import logging
import os
from queue import Empty
from threading import Thread
from time import time

from deployment.ftp import Ftp


class Worker(Thread):
    MODE_UPLOAD = "upload"
    MODE_REMOVE = "remove"

    running = True
    mode = None
    prefix = None
    size = None
    written = 0
    percent = None
    next_percent_update = 0

    def __init__(self, queue, config, counter, index, failed, mode, mapping):
        super(Worker, self).__init__()
        self.daemon = True

        self.queue = queue
        self.failed = failed
        self.mode = mode
        self.config = config
        self.counter = counter
        self.index = index
        self.mapping = mapping
        self.ftp = Ftp(self.config)

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

                local = path
                remote = self.apply_mapping(path)
                if local == remote:
                    local = self.config.local + local

                try:
                    if local and remote:
                        if self.mode == self.MODE_UPLOAD:
                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                self.prefix = "Retrying to upload (" + counter + ") " + remote
                                logging.info(self.prefix)
                            else:
                                self.prefix = "Uploading (" + self.counter.counter() + ") " + remote
                                logging.info(self.prefix)

                            self.upload(local, remote)
                            self.index.write(local)

                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                logging.info("Repeated upload (" + counter + ") " + remote + " WAS SUCCESSFUL")

                        elif self.mode == self.MODE_REMOVE:
                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                logging.info("Retrying to remove (" + counter + ") " + remote)
                            else:
                                logging.info("Removing (" + self.counter.counter() + ") " + remote)

                            self.ftp.delete_file_or_directory(remote)

                            if retry > 0:
                                counter = str(retry) + " of " + str(self.config.retry_count)
                                logging.info("Repeated remove (" + counter + ") " + remote + " WAS SUCCESSFUL")

                    self.queue.task_done()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    if retry < self.config.retry_count:
                        self.queue.put({
                            "path": remote,
                            "retry": retry + 1,
                        })
                    else:
                        logging.exception(e)
                        self.failed.put(self.mode + " " + remote + " (" + str(e) + ")")

                    self.ftp.close()

                    self.queue.task_done()
            except Empty:
                pass

        self.ftp.close()

    def upload(self, local, remote):
        remote = self.config.remote + remote

        if os.path.isdir(local):
            self.ftp.create_directory(remote)
        elif os.path.isfile(local):
            self.size = os.path.getsize(local)
            if self.size > (1024 * 1024):
                self.percent = 0
                self.next_percent_update = 0
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
            if self.next_percent_update < time():
                logging.info(self.prefix + " [" + str(self.percent) + "%]")
            self.next_percent_update = time() + 2

    def apply_mapping(self, path):
        for mapped, original in self.mapping.items():
            if path.startswith(original) or path == original:
                path = path.replace(original, mapped)
        return path

    def stop(self):
        self.running = False
