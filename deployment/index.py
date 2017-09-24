import bz2
from collections import OrderedDict
import logging
from multiprocessing import Lock
import os

from common.singleton import Singleton
from config import Config
from ftp import Ftp


class Index:
    __metaclass__ = Singleton

    FILE_NAME = "/.deployment-index"
    BACKUP_FILE_NAME = "/.deployment-index.backup"

    file = None
    lock = Lock()
    times = {}

    def __init__(self):
        self.config = Config()
        self.ftp = Ftp()

        self.file_path = self.config.local + self.FILE_NAME
        self.backup_path = self.config.local + self.BACKUP_FILE_NAME

    def read(self):
        remove = True

        if os.path.isfile(self.backup_path):
            with open(self.backup_path, "r") as file:
                contents = file.readlines()
            remove = False
        else:
            logging.info("Downloading index...")
            contents = self.ftp.download_file_bytes(self.config.remote + self.FILE_NAME)
            logging.info("Index downloaded")

            if contents:
                try:
                    contents = bz2.decompress(contents)
                    contents = contents.decode("utf-8")
                    lines = contents.split("\n")
                    contents = OrderedDict()
                    for line in lines:
                        if line:
                            parts = line.split(" ", 1)

                            if len(parts) != 2:
                                continue

                            time = parts[0].strip()
                            path = parts[1].strip()

                            if time == "None":
                                time = None

                            contents[path] = time
                except IOError:
                    pass

        return {
            "remove": remove,
            "contents": contents
        }

    def write(self, path):
        self.lock.acquire()

        time = None
        if path in self.times:
            time = self.times[path]

        if not self.file:
            if os.path.isfile(self.file_path) and not os.path.isfile(self.backup_path):
                os.rename(self.file_path, self.backup_path)
            self.file = bz2.BZ2File(self.file_path, "w")

        self.file.write(str(time) + " " + path + "\n")

        self.lock.release()

    def upload(self):
        self.close()

        local = self.config.local + self.FILE_NAME
        remote = self.config.remote + self.FILE_NAME
        if self.ftp.upload_file(local, remote, None):
            os.remove(local)

    def close(self):
        if self.file is not None:
            self.file.close()
