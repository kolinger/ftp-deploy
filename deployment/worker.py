import ftplib
import logging
import os
from queue import Empty
import sys
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
    phase = "init"
    local_counter = 0

    def __init__(self, queue, config, counter, index, failed, mode, mapping, state):
        super(Worker, self).__init__(daemon=True)

        self.queue = queue
        self.failed = failed
        self.mode = mode
        self.config = config
        self.counter = counter
        self.index = index
        self.mapping = mapping
        self.shared_state = state
        self.ftp = Ftp(self.config)

    def run(self):
        try:
            while self.shared_state.running:
                try:
                    self.phase = "fetch"
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

                                self.phase = "upload"
                                self.upload(path)

                                self.phase = "index"
                                self.index.write(path)

                            elif self.mode == self.MODE_REMOVE:
                                if retry > 0:
                                    counter = str(retry) + " of " + str(self.config.retry_count)
                                    logging.info("Retrying to remove (" + counter + ") " + path)
                                else:
                                    logging.info("Removing (" + self.counter.counter() + ") " + path)

                                self.phase = "delete"
                                self.ftp.delete_file_or_directory(self.config.remote + path)

                        self.phase = "done"
                        self.queue.task_done()
                        self.local_counter += 1
                    except ftplib.all_errors as e:
                        self.phase = "error"
                        logging.warning("Upload of " + path + " failed, will retry later, reason: " + str(e))

                        if retry < self.config.retry_count:
                            self.queue.put({
                                "path": path,
                                "retry": retry + 1,
                            })
                        else:
                            logging.exception(e)
                            self.failed.put(self.mode + " " + path + " (" + str(e) + ")")

                        self.phase = "close"
                        self.ftp.close()

                        self.queue.task_done()
                except Empty:
                    pass
        except (KeyboardInterrupt, SystemExit):
            self.shared_state.stop()
        except:
            self.shared_state.stop()
            logging.exception(sys.exc_info()[0])
        finally:
            self.ftp.close()
            self.running = False

    def upload(self, remote):
        local = self.apply_mapping(remote)
        if local == remote:
            local = self.config.local + local
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
        else:
            raise Exception(local + " doesn't exist!")

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
        for remote, local in self.mapping.items():
            if path.startswith(remote):
                return path.replace(remote, local)
        return path


class WorkersState:
    running = True

    def stop(self):
        self.running = False
