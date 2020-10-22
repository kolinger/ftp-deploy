import ftplib
import logging
import os
from queue import Empty
from queue import Queue
import sys
from threading import Thread

from deployment.ftp import Ftp
from deployment.worker import WorkersState


class Purge:
    TYPE_FILE = "file"
    TYPE_DIRECTORY = "directory"
    TYPE_LISTING = "listing"
    TYPE_UNKNOWN = "unknown"

    queue = Queue()
    workers = []

    def __init__(self, config):
        self.config = config
        self.shared_state = WorkersState()

    def add(self, path):
        self.queue.put((path, self.TYPE_UNKNOWN))

    def process(self):
        self.workers = []
        threads = self.config.threads if self.config.purge_threads is None else self.config.purge_threads
        logging.info("Using " + str(threads) + " threads")
        for number in range(threads):
            worker = Worker(self.queue, self.config, self.shared_state)
            worker.start()
            self.workers.append(worker)

        with self.queue.all_tasks_done:
            while self.queue.unfinished_tasks and self.shared_state.running:
                try:
                    self.queue.all_tasks_done.wait(0.1)
                except TimeoutError:
                    pass

        if self.queue.unfinished_tasks:
            logging.error("Worker queue failed to process")

        self.shared_state.stop()
        for worker in self.workers:
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

    def __init__(self, queue, config, shared_state):
        super(Worker, self).__init__(daemon=True)
        self.queue = queue
        self.config = config
        self.shared_state = shared_state
        self.ftp = Ftp(self.config)

    def run(self):
        try:
            while self.shared_state.running:
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
                            except (ExpectedError, EOFError):
                                type = Purge.TYPE_LISTING

                        elif type is Purge.TYPE_FILE:
                            try:
                                self.retry(self.ftp.delete_file, {"file": parent}, "operation failed")
                                self.files += 1
                            except EOFError:
                                parent = os.path.dirname(parent)
                                type = Purge.TYPE_LISTING
                            except ExpectedError:
                                pass

                        elif type is Purge.TYPE_DIRECTORY:
                            try:
                                self.retry(self.ftp.delete_directory, {"directory": parent, "verify": True}, [
                                    "directory not empty",
                                    "operation failed",
                                ])
                                self.directories += 1
                            except (ExpectedError, EOFError):
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
                            try:
                                for path, kind in self.retry(self.ftp.list_directory_contents, parameters, fallback=[]):
                                    path = parent + "/" + path
                                    if kind == "file":
                                        self.queue.put((path, Purge.TYPE_FILE))
                                    else:
                                        self.queue.put((path, Purge.TYPE_LISTING))

                                self.queue.put((parent, Purge.TYPE_DIRECTORY))
                            except EOFError:
                                pass

                        self.queue.task_done()
                    except (KeyboardInterrupt, SystemExit):
                        raise
                    except ftplib.all_errors as e:
                        self.ftp.close()

                        logging.exception(e)

                        self.queue.task_done()
                except Empty:
                    pass

        except (KeyboardInterrupt, SystemExit):
            self.shared_state.stop()
            raise
        except:
            self.shared_state.stop()
            logging.exception(sys.exc_info()[0])
        finally:
            self.ftp.close()
            self.running = False

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
