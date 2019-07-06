from ftplib import error_perm
import logging
import os
import queue
from queue import Queue
import re
import time

from deployment.composer import Composer
from deployment.counter import Counter
from deployment.ftp import Ftp
from deployment.index import Index
from deployment.process import Process
from deployment.scanner import Scanner
from deployment.worker import Worker


class Deployment:
    mapping = {}
    extensions = []

    def __init__(self, config):
        self.config = config
        self.counter = Counter()
        self.index = Index(self.config)
        self.ftp = Ftp(self.config)
        self.failed = Queue()

    def deploy(self, run_before_skip, purge_partial_enabled):
        result = self.index.read()
        remove = result["remove"]
        contents = result["contents"]
        roots = [self.config.local]

        if len(self.config.purge_partial) == 0:
            purge_partial_enabled = False

        if os.name == "nt":
            for index, value in enumerate(roots):
                roots[index] = value.replace("\\", "/")

        if self.config.composer:
            composer = Composer(self.config)
            remote, local = composer.process()

            # add another root so live vendor is scanned
            roots.append(local.replace(remote, ""))

            # map development vendor to live
            self.mapping[remote] = local

            # map also .json and .lock files from live vendor
            remote_base = os.path.dirname(remote)
            local_base = os.path.dirname(local)
            for file in ["composer.json", "composer.lock"]:
                self.mapping[remote_base + "/" + file] = local_base + "/" + file

            # ignore development vendor
            self.config.ignore.append(remote)

        if len(self.config.run_before) > 0:
            if run_before_skip:
                logging.info("Skipping before commands")
            else:
                logging.info("Running before commands:")
                self.run_commands(self.config.run_before)

        logging.info("Scanning...")
        scanner = Scanner(self.config, roots, self.config.ignore, self.mapping)
        self.index.hashes = objects = scanner.scan()

        logging.info("Calculating changes...")

        uploadQueue = Queue()
        to_delete = []

        offset = 0
        if contents is None:
            for path in objects:
                self.store_extension(path)
                uploadQueue.put(path)
        else:
            for path in objects:
                checksum = objects[path]
                if path in contents and (checksum is None or checksum == contents[path]):
                    self.index.write(path)
                else:
                    self.store_extension(path)
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
                removeQueue.put(path)

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

            to_purge = self.config.purge
            extension_count = len(self.extensions)
            if extension_count > 0 and purge_partial_enabled:
                to_purge = []
                for extension in self.extensions:
                    if extension in self.config.purge_partial:
                        to_purge.append(self.config.purge_partial[extension])

            to_delete = []
            base_folders = {}
            suffix = str(int(time.time())) + ".tmp"
            for path in to_purge:
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

            for base, names in base_folders.items():
                objects = self.ftp.list_directory_contents(base)
                for object in objects:
                    for name in names:
                        if re.search(r"^" + name + r"_[0-9]+\.tmp$", object):
                            to_delete.append(base + "/" + object)

            for path in to_delete:
                try:
                    self.ftp.delete_recursive(path)
                    self.ftp.delete_file_or_directory(path)
                except error_perm:
                    pass

            logging.info("Purging done")

        if len(self.config.run_after) > 0:
            if skip:
                logging.info("Skipping after commands")
            else:
                logging.info("Running after commands:")
                self.run_commands(self.config.run_after)

        if not self.failed.empty():
            logging.fatal("FAILED TO PROCESS FOLLOWING OBJECTS")
            while True:
                try:
                    object = self.failed.get_nowait()
                    logging.fatal("failed to " + object)
                except queue.Empty:
                    break

    def process_queue(self, queue, mode):
        workers = []
        for number in range(self.config.threads):
            worker = Worker(queue, self.config, self.counter, self.index, self.failed, mode, self.mapping)
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

    def store_extension(self, path):
        extension = os.path.splitext(path)[1][1:]
        if extension and extension not in self.extensions:
            self.extensions.append(extension)

    def run_commands(self, list):
        def callback(line):
            logging.info(line)

        for command in list:
            logging.info("Command " + command + " started")
            process = Process(command).execute(None, callback)
            if process.return_code() != 0:
                logging.info("Command " + command + " failed with return code: " + str(process.return_code()))
                exit(1)
            else:
                logging.info("Command " + command + " ended with return code: " + str(process.return_code()))
