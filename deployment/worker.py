from Queue import Empty
from ftplib import error_perm
import logging
import os
from threading import Thread

from config import Config
from counter import Counter
from ftp import Ftp
from index import Index


class Worker(Thread):
    MODE_UPLOAD = "upload"
    MODE_REMOVE = "remove"

    mode = None
    prefix = None
    size = None
    written = 0
    percent = None

    def __init__(self, queue, mode):
        super(Worker, self).__init__()
        self.daemon = True

        self.mode = mode
        self.queue = queue
        self.config = Config()
        self.counter = Counter()
        self.index = Index()
        self.ftp = Ftp()

    def run(self):
        while not self.queue.empty():
            try:
                path = self.queue.get_nowait()
                if path:
                    if self.mode == self.MODE_UPLOAD:
                        self.prefix = "Uploading (" + self.counter.counter() + ") " + path
                        logging.info(self.prefix)
                        if self.upload(path):
                            self.index.write(path)
                    elif self.mode == self.MODE_REMOVE:
                        self.prefix = "Removing (" + self.counter.counter() + ") " + path
                        logging.info(self.prefix)

                        try:
                            self.ftp.delete_file_or_directory(path)
                        except error_perm:
                            if not self.queue.empty():
                                self.queue.put(path)

                self.queue.task_done()
            except Empty:
                pass

        self.ftp.close()

    def upload(self, path):
        local = self.config.local + path
        remote = self.config.remote + path

        if os.path.isdir(local):
            return self.ftp.create_directory(remote)
        elif os.path.isfile(local):
            self.size = os.path.getsize(local)
            if self.size > (1024 * 1024):
                callback = self.upload_progress
            else:
                callback = None
            return self.ftp.upload_file(local, remote, callback)

        return False

    def upload_progress(self, block):
        self.written += 1024
        percent = int(round((float(self.written) / float(self.size)) * 100))

        if self.percent != percent:
            self.percent = percent
            if self.percent > 100:
                self.percent = 100
            logging.info(self.prefix + " [" + str(self.percent) + "%]")
