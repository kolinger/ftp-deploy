import os
from multiprocessing import Lock

from common.singleton import Singleton
from config import Config
from ftp import Ftp


class Index:
    __metaclass__ = Singleton

    FILE_NAME = "/.deployment-index"
    BACKUP_FILE_NAME = "/.deployment-index.backup"

    file = None
    lock = Lock()
    hashes = {}

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
            contents = self.ftp.download_file_contents(self.config.remote + self.FILE_NAME)
            if contents:
                contents = contents.split("\n")

        return {
            "remove": remove,
            "contents": contents
        }

    def write(self, path):
        self.lock.acquire()

        hash = None
        if path in self.hashes:
            hash = self.hashes[path]

        if not self.file:
            if os.path.isfile(self.file_path) and not os.path.isfile(self.backup_path):
                os.rename(self.file_path, self.backup_path)
            self.file = open(self.file_path, "w")

        self.file.write(str(hash) + " " + path + "\n")
        self.file.flush()

        self.lock.release()

    def upload(self):
        if self.file:
            self.file.close()

        local = self.config.local + self.FILE_NAME
        remote = self.config.remote + self.FILE_NAME
        if self.ftp.upload_file(local, remote, None):
            os.remove(local)
