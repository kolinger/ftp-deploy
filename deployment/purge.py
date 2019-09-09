import ftplib
import logging
from queue import Empty
from queue import Queue
from threading import Thread

from deployment.ftp import Ftp


class Purge:
    TYPE_FILE = "file"
    TYPE_DIRECTORY = "directory"
    TYPE_LISTING = "listing"
    TYPE_UNKNOWN = "unknown"

    queue = Queue()
    workers = []

    def __init__(self, config):
        self.config = config

    def add(self, path):
        self.queue.put((path, self.TYPE_UNKNOWN))

    def process(self):
        self.workers = []
        for number in range(self.config.threads):
            worker = Worker(self.queue, self.config)
            worker.start()
            self.workers.append(worker)

        self.queue.join()

        for worker in self.workers:
            worker.stop()
            worker.join()

        return self.count()

    def count(self):
        directories = 0
        files = 0

        for worker in self.workers:
            directories += worker.directories
            files += worker.files

        return directories, files


class Worker(Thread):
    running = True
    directories = 0
    files = 0
    not_empty = {}

    def __init__(self, queue, config):
        super(Worker, self).__init__()
        self.daemon = True

        self.queue = queue
        self.config = config
        self.ftp = Ftp(self.config)

    def run(self):
        while self.running:
            try:
                parent, type = self.queue.get_nowait()

                try:
                    if type is Purge.TYPE_UNKNOWN or type is Purge.TYPE_LISTING:
                        logging.info("Cleaning " + parent)

                    if type is Purge.TYPE_UNKNOWN:
                        try:
                            self.retry(self.ftp.delete_file, {"file": parent}, [
                                "invalid argument",
                                "operation failed",
                                "is a directory",
                            ])
                        except ExpectedError:
                            type = Purge.TYPE_LISTING

                    elif type is Purge.TYPE_FILE:
                        try:
                            self.retry(self.ftp.delete_file, {"file": parent}, "operation failed")
                            self.files += 1
                        except ExpectedError:
                            pass

                    elif type is Purge.TYPE_DIRECTORY:
                        try:
                            self.retry(self.ftp.delete_directory, {"directory": parent, "verify": True}, [
                                "directory not empty",
                                "operation failed",
                            ])
                            self.directories += 1
                        except ExpectedError:
                            if parent not in self.not_empty:
                                self.not_empty[parent] = 0
                            self.not_empty[parent] += 1

                            if self.not_empty[parent] > 5:
                                self.not_empty[parent] = -20
                                self.queue.put((parent, Purge.TYPE_LISTING))
                            else:
                                self.queue.put((parent, Purge.TYPE_DIRECTORY))

                    if type is Purge.TYPE_LISTING:
                        parameters = {
                            "directory": parent,
                            "extended": True,
                        }
                        for path, kind in self.retry(self.ftp.list_directory_contents, parameters, fallback=[]):
                            path = parent + "/" + path
                            if kind == "file":
                                self.queue.put((path, Purge.TYPE_FILE))
                            else:
                                self.queue.put((path, Purge.TYPE_LISTING))

                        self.queue.put((parent, Purge.TYPE_DIRECTORY))

                    self.queue.task_done()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except ftplib.all_errors as e:
                    self.ftp.close()

                    logging.exception(e)

                    self.queue.task_done()
            except Empty:
                pass

        self.ftp.close()

    def stop(self):
        self.running = False

    def retry(self, callable, arguments, expected_error=None, fallback=None):
        if expected_error and not isinstance(expected_error, list):
            expected_error = [expected_error]

        retries = 10
        while True:
            try:
                if arguments:
                    return callable(**arguments)
                else:
                    return callable()
            except ftplib.all_errors as e:
                message = str(e).lower()

                if "no such file or directory" in message:
                    break

                if expected_error and isinstance(e, ftplib.error_perm):
                    for string in expected_error:
                        if string in message:
                            raise ExpectedError(e)

                if isinstance(e, EOFError) or isinstance(e, OSError):
                    self.ftp.close()

                retries -= 1
                if retries == 0:
                    raise e

        return fallback


class ExpectedError(Exception):
    pass
