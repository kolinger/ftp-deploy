import ftplib
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

    def delete_recursive(self, target):
        self.connect()

        self._retry(
            self._delete_recursive_helper, {"target": target},
            "Retrying deletion of " + target,
            "Failed to delete " + target
        )

    def _delete_recursive_helper(self, target):
        try:
            self.ftp.delete(target)
        except error_perm:
            try:
                self.ftp.cwd(target)
                self._delete_recursive_list_helper()
            except error_perm as e:
                message = str(e)
                if "No such file or directory" in message:
                    return
                raise e

    def _delete_recursive_list_helper(self):
        path = self.ftp.pwd()
        logging.info("Cleaning " + path)

        for object in self.ftp.nlst():
            if object == "." or object == "..":
                continue

            self._retry(
                self._delete_recursive_object_helper, {"object": object},
                "Retrying deletion of " + path,
                "Failed to delete " + path
            )

    def _delete_recursive_object_helper(self, object):
        try:
            self.ftp.delete(object)
        except error_perm:
            # object is directory
            self.ftp.cwd(object)
            self._delete_recursive_list_helper()
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

    def _retry(self, callable, arguments, retry_message, failed_message):
        retries = 10
        while True:
            try:
                if arguments:
                    callable(**arguments)
                else:
                    callable()
                break
            except ftplib.all_errors as e:
                retries -= 1
                if retries == 0:
                    logging.fatal(failed_message)
                    raise e
                logging.warning(retry_message + " due to error: " + str(e))
