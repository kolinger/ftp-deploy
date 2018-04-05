from Queue import Queue
from ftplib import error_perm
import logging
import os
import re
import time

from counter import Counter
from ftp import Ftp
from index import Index
from scanner import Scanner
from worker import Worker


class Deployment:
    def __init__(self, config):
        self.config = config
        self.counter = Counter()
        self.index = Index(self.config)
        self.ftp = Ftp(self.config)
        self.failed = Queue()

    def deploy(self):
        result = self.index.read()
        remove = result["remove"]
        contents = result["contents"]

        logging.info("Scanning...")
        scanner = Scanner(self.config, self.config.local, self.config.ignore)
        self.index.times = objects = scanner.scan()

        logging.info("Calculating changes...")

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

            self.counter.total = uploadQueue.qsize() + offset
            self.counter.count = 1 + offset

            self.process_queue(uploadQueue, Worker.MODE_UPLOAD)

            logging.info("Uploading done")

        if len(to_delete) == 0:
            logging.info("Nothing to remove")
        else:
            logging.info("Removing...")

            removeQueue = Queue()
            for path in reversed(to_delete):
                removeQueue.put(self.config.remote + path)

            self.counter.reset()
            self.counter.total = removeQueue.qsize()

            self.process_queue(removeQueue, Worker.MODE_REMOVE)

            logging.info("Removing done")

        logging.info("Uploading index...")
        self.index.upload()
        logging.info("Index uploaded")

        if len(self.config.purge) == 0:
            logging.info("Nothing to purge")
        else:
            logging.info("Purging...")

            to_delete = []
            base_folders = {}
            suffix = str(int(time.time())) + ".tmp"
            for path in self.config.purge:
                current = self.config.remote + path

                name = os.path.basename(current)
                base = os.path.dirname(current)
                if base not in base_folders:
                    base_folders[base] = []
                if name not in base_folders[base]:
                    base_folders[base].append(name)

                try:
                    self.ftp.delete_file(current)
                except error_perm:
                    try:
                        new = current + "_" + suffix
                        self.ftp.rename(current, new)
                        to_delete.append(new)
                        self.ftp.create_directory(current)
                    except error_perm:
                        pass

            for base, names in base_folders.iteritems():
                objects = self.ftp.list_directory_contents(base)
                for object in objects:
                    for name in names:
                        if re.search("^" + name + "_[0-9]+\.tmp$", object):
                            to_delete.append(base + "/" + object)

            for path in to_delete:
                try:
                    self.ftp.delete_recursive(path)
                    self.ftp.delete_file_or_directory(path)
                except error_perm:
                    pass

            logging.info("Purging done")

        if not self.failed.empty():
            logging.fatal("FAILED TO PROCESS FOLLOWING OBJECTS")
            for object in list(self.failed.queue):
                logging.fatal("failed to " + object)

    def process_queue(self, queue, mode):
        workers = []
        for number in range(self.config.threads):
            worker = Worker(queue, self.config, self.counter, self.index, self.failed, mode)
            worker.start()
            workers.append(worker)

        wait = True
        while wait:
            wait = not queue.empty()
            if not wait:
                time.sleep(1)
                wait = not queue.empty()

        for worker in workers:
            worker.stop()
            worker.join()

    def close(self):
        self.index.close()
        self.ftp.close()
