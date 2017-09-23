from Queue import Queue
from ftplib import error_perm
import logging
import os

from config import Config
from counter import Counter
from ftp import Ftp
from index import Index
from scanner import Scanner
from uploadworker import UploadWorker


class Deployment:
    def __init__(self):
        self.config = Config()
        self.counter = Counter()
        self.index = Index()
        self.ftp = Ftp()
        self.queue = Queue()

    def deploy(self):
        logging.info("Scanning...")
        scanner = Scanner(self.config.local, self.config.ignore)
        self.index.times = objects = scanner.scan()

        logging.info("Calculating changes...")

        to_delete = []

        result = self.index.read()
        remove = result["remove"]
        contents = result["contents"]

        offset = 0
        if contents is None:
            for path in objects:
                self.queue.put(path)
        else:
            for path in objects:
                time = objects[path]
                if path in contents and (time is None or time == contents[path]):
                    self.index.write(path)
                else:
                    self.queue.put(path)

            if os.path.isfile(self.index.backup_path):
                os.remove(self.index.backup_path)

            if remove:
                for path in contents:
                    if path not in objects:
                        to_delete.append(path)
            else:
                offset = len(contents)

        self.counter.total = str(self.queue.qsize() + offset)
        self.counter.count = 1 + offset

        for number in range(self.config.threads):
            worker = UploadWorker(self.queue)
            worker.start()

        self.queue.join()

        logging.info("Uploading done")

        for path in reversed(to_delete):
            try:
                logging.info("Removing " + path)
                self.ftp.delete_file_or_directory(self.config.remote + path)
            except error_perm as e:
                logging.exception(e)

        logging.info("Removing done")

        self.index.upload()

        logging.info("Index uploaded")

        self.purge()

        self.ftp.close()

    def purge(self):
        for path in self.config.purge:
            try:
                self.ftp.delete_recursive(self.config.remote + path)
            except error_perm as e:
                pass
