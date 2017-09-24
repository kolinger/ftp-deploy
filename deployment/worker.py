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

    running = True
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
        while self.running:
            try:
                value = self.queue.get_nowait()
                if type(value) is dict:
                    path = value["path"]
                    retry = value["retry"]
                else:
                    path = value
                    retry = 0

                try:
                    if path:
                        if self.mode == self.MODE_UPLOAD:
                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                self.prefix = "Retrying to upload (" + counter + ") " + path
                                logging.info(self.prefix)
                            else:
                                self.prefix = "Uploading (" + self.counter.counter() + ") " + path
                                logging.info(self.prefix)

                            self.upload(path)
                            self.index.write(path)

                        elif self.mode == self.MODE_REMOVE:
                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                logging.info("Retrying to remove (" + counter + ") " + path)
                            else:
                                logging.info("Removing (" + self.counter.counter() + ") " + path)

                            self.ftp.delete_file_or_directory(path)

                    self.queue.task_done()
                except error_perm as e:
                    if retry < self.config.retry_count:
                        self.queue.put({
                            "path": path,
                            "retry": retry + 1,
                        })
                    else:
                        logging.exception(e)
                        self.queue.task_done()
            except Empty:
                pass

        self.ftp.close()

    def upload(self, path):
        local = self.config.local + path
        remote = self.config.remote + path

        if os.path.isdir(local):
            self.ftp.create_directory(remote)
        elif os.path.isfile(local):
            self.size = os.path.getsize(local)
            if self.size > (1024 * 1024):
                callback = self.upload_progress
            else:
                callback = None
            self.ftp.upload_file(local, remote, callback)

    def upload_progress(self, block):
        self.written += len(block)
        percent = int(round((float(self.written) / float(self.size)) * 100))

        if self.percent != percent:
            self.percent = percent
            if self.percent > 100:
                self.percent = 100
            logging.info(self.prefix + " [" + str(self.percent) + "%]")

    def stop(self):
        self.running = False
