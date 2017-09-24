from cStringIO import StringIO
from ftplib import FTP, FTP_TLS, error_perm
import logging
import os

from config import Config


class Ftp:
    ftp = None

    def __init__(self):
        self.config = Config()

    def connect(self):
        if not self.ftp:
            if self.config.secure:
                self.ftp = FTP_TLS(self.config.host, self.config.user, self.config.password)
            else:
                self.ftp = FTP(self.config.host, self.config.user, self.config.password)

        return self.ftp

    def rename(self, current, new):
        self.connect()

        self.ftp.rename(current, new)

    def create_directory(self, directory):
        self.connect()

        try:
            self.ftp.mkd(directory)
        except error_perm as e:
            if e.message.startswith("550"):
                return  # already exists - ignore
            raise e

    def upload_file(self, local, remote, callback):
        self.connect()

        if os.path.isfile(local):
            with open(local, "rb") as file:
                directory = remote
                while True:
                    try:
                        self.ftp.storbinary("STOR " + remote, file, 8192, callback)
                        return True
                    except error_perm as e:
                        if e.message.startswith("553"):  # directory not exists
                            directory = os.path.dirname(directory)
                            if directory == "/":
                                return False
                            self.create_directory(directory)
                            continue

                        return False

    def download_file_contents(self, file):
        self.connect()

        try:
            buffer = StringIO()
            self.ftp.retrbinary("RETR " + file, buffer.write)
            return buffer.getvalue()
        except error_perm as e:
            if e.message.startswith("550"):
                return None  # not exists - ignore
            logging.error("File download failed, reason: " + e.message)
        return None

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
                    if e.message.startswith("550"):  # directory not exists
                        directory = os.path.dirname(directory)
                        if directory == "/":
                            return
                        self.create_directory(directory)
                        continue
                    raise e

    def delete_directory(self, directory):
        self.connect()

        try:
            self.ftp.rmd(directory)
            return True
        except error_perm as e:
            logging.error("Directory deletion failed, reason: " + e.message)

        return False

    def list_directory_contents(self, directory, callback):
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
                if "No such file or directory" in e.message:
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
            self.ftp.quit()
