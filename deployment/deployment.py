from Queue import Queue
from ftplib import error_perm
import logging
import os
import time

from config import Config
from counter import Counter
from ftp import Ftp
from index import Index
from scanner import Scanner
from worker import Worker


class Deployment:
    def __init__(self):
        self.config = Config()
        self.counter = Counter()
        self.index = Index()
        self.ftp = Ftp()

    def deploy(self):
        logging.info("Scanning...")
        scanner = Scanner(self.config.local, self.config.ignore)
        self.index.times = objects = scanner.scan()

        logging.info("Calculating changes...")

        result = self.index.read()
        remove = result["remove"]
        contents = result["contents"]

        uploadQueue = Queue()
        to_delete = []

        offset = 0
        if contents is None:
            for path in objects:
                uploadQueue.put(path)
        else:
            for path in objects:
                modification_time = objects[path]
                if path in contents and (modification_time is None or modification_time == contents[path]):
                    self.index.write(path)
                else:
                    uploadQueue.put(path)

            if os.path.isfile(self.index.backup_path):
                os.remove(self.index.backup_path)

            if remove:
                for path in contents:
                    if path not in objects:
                        to_delete.append(path)
            else:
                offset = len(contents)

        if uploadQueue.qsize() == 0:
            logging.info("Nothing to upload")
        else:
            logging.info("Uploading...")

            self.counter.total = str(uploadQueue.qsize() + offset)
            self.counter.count = 1 + offset

            for number in range(self.config.threads):
                worker = Worker(uploadQueue, Worker.MODE_UPLOAD)
                worker.start()

            uploadQueue.join()

            logging.info("Uploading done")

        if len(to_delete) == 0:
            logging.info("Nothing to remove")
        else:
            logging.info("Removing...")

            removeQueue = Queue()
            for path in reversed(to_delete):
                removeQueue.put(self.config.remote + path)

            self.counter.total = str(removeQueue.qsize())
            self.counter.count = 1

            for number in range(self.config.threads):
                worker = Worker(removeQueue, Worker.MODE_REMOVE)
                worker.start()

            removeQueue.join()

            logging.info("Removing done")

        self.index.upload()

        logging.info("Index uploaded")

        if len(self.config.purge) == 0:
            logging.info("Nothing to purge")
        else:
            logging.info("Purging...")

            to_delete = []
            suffix = str(int(time.time()))
            for path in self.config.purge:
                current = self.config.remote + path
                new = current + "_" + suffix
                to_delete.append(new)

                try:
                    self.ftp.rename(current, new)
                    self.ftp.create_directory(current)
                except error_perm:
                    pass

            for path in to_delete:
                logging.info("Cleaning " + path)
                try:
                    self.ftp.delete_recursive(path)
                    self.ftp.delete_file_or_directory(path)
                except error_perm:
                    pass

            logging.info("Purging done")

        self.ftp.close()
