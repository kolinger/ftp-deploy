import bz2
from collections import OrderedDict
import ftplib
import logging
from multiprocessing import Lock
import os

from deployment.exceptions import DownloadFailedException
from deployment.ftp import Ftp


class Index:
    FILE_NAME = "/.deployment-index"
    BACKUP_FILE_NAME = "/.deployment-index.backup"

    file = None
    lock = Lock()
    hashes = {}

    def __init__(self, config):
        self.config = config

        self.file_path = self.config.local + self.FILE_NAME
        self.backup_path = self.config.local + self.BACKUP_FILE_NAME

    def read(self):
        remove = True

        if os.path.isfile(self.file_path) and not os.path.isfile(self.backup_path):
            os.rename(self.file_path, self.backup_path)

        if os.path.isfile(self.backup_path):
            with open(self.backup_path, "rb") as file:
                contents = file.read()
            remove = False
        else:
            logging.info("Downloading index...")
            ftp = Ftp(self.config)
            contents = ftp.download_file_bytes(self.config.remote + self.FILE_NAME)
            ftp.close()
            if contents is False:
                raise DownloadFailedException("Index downloading failed")
            logging.info("Index downloaded")

        if contents:
            try:
                contents = bz2.decompress(contents)
            except IOError:
                pass

            try:
                contents = contents.decode("utf-8")
                lines = contents.split("\n")
                contents = OrderedDict()
                for line in lines:
                    if line:
                        parts = line.split(" ", 1)

                        if len(parts) != 2:
                            continue

                        value = parts[0].strip()
                        path = parts[1].strip()

                        if value == "None":
                            value = None

                        contents[path] = value
            except UnicodeDecodeError:
                logging.warning("Failed to parse contents of index - processing to upload everything")
                if os.path.isfile(self.file_path):
                    os.rename(self.file_path, self.backup_path)

        if type(contents) is not OrderedDict:
            contents = {}

        return {
            "remove": remove,
            "contents": contents
        }

    def write(self, path):
        self.lock.acquire()

        value = None
        if path in self.hashes:
            value = self.hashes[path]

        if not self.file:
            if os.path.isfile(self.file_path) and not os.path.isfile(self.backup_path):
                os.rename(self.file_path, self.backup_path)
            self.file = bz2.BZ2File(self.file_path, "w")

        line = str(value) + " " + path + "\n"
        self.file.write(line.encode("utf-8"))

        self.lock.release()

    def upload(self):
        self.close()

        local = self.config.local + self.FILE_NAME
        remote = self.config.remote + self.FILE_NAME
        retries = 10
        while True:
            ftp = Ftp(self.config)
            try:
                ftp.upload_file(local, remote, None)
                break
            except ftplib.all_errors as e:
                retries -= 1
                if retries == 0:
                    logging.fatal("Failed to upload index")
                    raise e
                logging.warning("Retrying to upload index due to error: " + str(e))
            finally:
                ftp.close()

        os.remove(local)

    def remove(self):
        self.close()
        path = self.config.local + self.FILE_NAME
        if os.path.exists(path):
            os.remove(path)

    def close(self):
        if self.file is not None:
            self.file.close()
