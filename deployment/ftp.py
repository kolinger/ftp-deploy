import ftplib
from io import BytesIO
import logging
import os
import platform
import re
from subprocess import check_output, CalledProcessError, STDOUT

from deployment.config import ConfigException
from deployment.exceptions import MessageException


class FTP_TLS(ftplib.FTP_TLS):
    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


class Ftp:
    ftp = None
    mlsd = True
    error_file_failed_no_directory = [
        "could not create file",
        "no such file or directory",
    ]

    def __init__(self, config):
        self.config = config

    def connect(self):
        if not self.ftp:
            if not self.config.host:
                raise ConfigException("host is missing")

            parameters = {
                "timeout": self.config.timeout,
            }
            if self.config.bind:
                address = self.translate_interface_to_address(self.config.bind)
                parameters["source_address"] = (address, 0)

            if self.config.secure:
                self.ftp = FTP_TLS(**parameters)
            else:
                self.ftp = ftplib.FTP(**parameters)

            self.ftp.connect(self.config.host)

            if self.config.secure and self.config.implicit:
                self.ftp.prot_p()

            self.ftp.login(self.config.user, self.config.password)
            self.ftp.set_pasv(self.config.passive)

        return self.ftp

    def rename(self, current, new):
        self.connect()

        self.ftp.rename(current, new)

    def create_directory(self, directory):
        self.connect()

        try:
            self.ftp.mkd(directory)
        except ftplib.error_perm as e:
            message = str(e)
            if message.startswith("550"):
                return  # already exists - ignore
            raise e

    def upload_file(self, local, remote, callback, ensure_directory=True):
        self.connect()

        with open(local, "rb") as file:
            try:
                self.ftp.storbinary("STOR " + remote, file, 8192, callback)
            except ftplib.all_errors as e:
                message = str(e).lower()
                if ensure_directory:
                    for error in self.error_file_failed_no_directory:
                        if error in message:
                            self.ensure_directory_exists(os.path.dirname(remote))
                            self.upload_file(local, remote, callback, False)
                            return

                raise e

    def ensure_directory_exists(self, path):
        previous = []
        for directory in path.split("/"):
            if directory == "":
                continue

            previous.append(directory)
            path = "/".join(previous)
            self.create_directory(path)

    def download_file_bytes(self, file):
        self.connect()

        try:
            buffer = BytesIO()
            self.ftp.retrbinary("RETR " + file, buffer.write)
            return buffer.getvalue()
        except ftplib.error_perm as e:
            message = str(e)
            if message.startswith("550"):
                return None  # not exists - ignore
            logging.error("File download failed, reason: " + message)
        return False

    def delete_file(self, file):
        self.connect()

        self.ftp.delete(file)

    def delete_file_or_directory(self, target):
        self.connect()

        try:
            self.ftp.delete(target)
        except ftplib.error_perm:
            directory = target
            while True:
                try:
                    self.ftp.rmd(directory)
                except ftplib.error_perm as e:
                    message = str(e)
                    if message.startswith("550"):  # directory not exists
                        return
                    raise e

    def delete_directory(self, directory, verify=False):
        self.connect()

        try:
            self.ftp.rmd(directory)
        except ftplib.error_perm:
            if not verify:
                raise
            try:
                self.ftp.cwd(directory)
                raise
            except ftplib.error_perm as e:
                if "failed to change directory" in str(e).lower():
                    return
                raise

    def list_directory_contents(self, directory, extended=False):
        self.connect()

        objects = []
        if extended:
            if self.mlsd:
                try:
                    for name, entry in self.ftp.mlsd(directory):
                        objects.append((name, entry["type"]))

                except ftplib.error_perm:
                    self.mlsd = False

                    lines = []
                    self.ftp.dir(directory, lines.append)
                    for line in lines:
                        parts = re.split(r"\s+", line)
                        name = parts[-1]
                        type = "dir" if parts[0][0] == "d" else "file"
                        objects.append((name, type))
        else:
            self.ftp.cwd(directory)
            for object in self.ftp.nlst():
                objects.append(object)

        filtered = []
        for object in objects:
            if isinstance(object, tuple):
                name, type = object
            else:
                name = object

            if name == "." or name == "..":
                continue

            filtered.append(object)

        return filtered

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                pass
            finally:
                self.ftp = None

    def translate_interface_to_address(self, bind):
        if re.match(r"^[0-9.]+$", bind):
            return bind

        if os.name == "nt" or "microsoft" in platform.uname()[2].lower():
            output = check_output("ipconfig.exe", shell=True)
            output = output.decode("ascii", errors="ignore")

            found = False
            for line in output.split("\n"):
                line = line.strip()

                match = re.match(r"^Ethernet adapter ([^:]+):$", line, flags=re.I)
                if match:
                    if match.group(1) == bind:
                        found = True
                        continue

                if found:
                    match = re.match(r"^IPv4 Address[\s.]*: ([0-9.]+)$", line, flags=re.I)
                    if match:
                        return match.group(1)

            if found:
                raise MessageException("address not found for interface " + bind)
            else:
                raise MessageException("interface " + bind + " not found")

        else:
            try:
                output = check_output("ip addr show " + bind, shell=True, stderr=STDOUT)
                output = output.decode("ascii", errors="ignore")
                match = re.search(r"^\s*inet ([0-9.]+)/[0-9]+", output, flags=re.I | re.M)
                if match:
                    return match.group(1)

                raise MessageException("address not found for interface " + bind)
            except CalledProcessError as e:
                if b"does not exist" in e.stdout:
                    raise MessageException("interface " + bind + " not found")
                else:
                    raise e
