import ftplib
from ftplib import FTP, FTP_TLS, error_perm
from io import BytesIO
import logging
import os
import re

from deployment.config import ConfigException


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

            if self.config.secure:
                self.ftp = FTP_TLS(self.config.host, self.config.user, self.config.password, timeout=10)
            else:
                self.ftp = FTP(self.config.host, self.config.user, self.config.password, timeout=10)

            self.ftp.set_pasv(self.config.passive)

        return self.ftp

    def rename(self, current, new):
        self.connect()

        self.ftp.rename(current, new)

    def create_directory(self, directory):
        self.connect()

        try:
            self.ftp.mkd(directory)
        except error_perm as e:
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
        except error_perm as e:
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
        except error_perm:
            directory = target
            while True:
                try:
                    self.ftp.rmd(directory)
                except error_perm as e:
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
                        if name == "." or name == "..":
                            continue

                        objects.append((name, entry["type"]))

                    return objects
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
                if object == "." or object == "..":
                    continue

                objects.append(object)

        return objects

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
