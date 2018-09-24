from ftplib import FTP, FTP_TLS, error_perm
from io import BytesIO
import logging
import os

from deployment.config import ConfigException


class Ftp:
    ftp = None

    def __init__(self, config):
        self.config = config

    def connect(self):
        if not self.ftp:
            if not self.config.host:
                raise ConfigException("host is missing")

            if self.config.secure:
                self.ftp = FTP_TLS(self.config.host, self.config.user, self.config.password)
            else:
                self.ftp = FTP(self.config.host, self.config.user, self.config.password)

            self.ftp.set_pasv(True)

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

    def upload_file(self, local, remote, callback):
        self.connect()

        with open(local, "rb") as file:
            directory = remote
            while True:
                try:
                    self.ftp.storbinary("STOR " + remote, file, 8192, callback)
                    break
                except error_perm as e:
                    message = str(e)
                    if message.startswith("553") or message.startswith("550"):  # directory not exists
                        directory = os.path.dirname(directory)
                        if directory == "/":
                            raise e
                        self.create_directory(directory)
                        continue

                    raise e

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

    def delete_directory(self, directory):
        self.connect()

        try:
            self.ftp.rmd(directory)
        except error_perm as e:
            message = str(e)
            logging.error("Directory deletion failed, reason: " + message)
            raise e

    def list_directory_contents(self, directory):
        self.connect()

        self.ftp.cwd(directory)

        objects = []
        for object in self.ftp.nlst():
            if object == "." or object == "..":
                continue

            objects.append(object)

        return objects

    def list_directory_contents_recursive(self, directory, callback):
        self.connect()

        self.ftp.cwd(directory)

        self._list_directory_contents_recursive(callback)

    def _list_directory_contents_recursive(self, callback):
        self.connect()

        for object in self.ftp.nlst():
            if object == "." or object == "..":
                continue

            callback(object)

            try:
                self.ftp.cwd(object)
                self._list_directory_contents_recursive(callback)
                self.ftp.cwd("..")
            except error_perm:
                pass

    def delete_recursive(self, target):
        self.connect()

        try:
            self.ftp.delete(target)
        except error_perm:
            try:
                self.ftp.cwd(target)
                self._delete_directory_contents_recursive()
            except error_perm as e:
                message = str(e)
                if "No such file or directory" in message:
                    return
                raise e

    def _delete_directory_contents_recursive(self):
        self.connect()

        logging.info("Cleaning " + self.ftp.pwd())

        for object in self.ftp.nlst():
            if object == "." or object == "..":
                continue
            try:
                self.ftp.delete(object)
            except error_perm:
                # object is directory
                self.ftp.cwd(object)
                self._delete_directory_contents_recursive()
                self.ftp.cwd("..")
                self.delete_directory(object)

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
