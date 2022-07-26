from ftplib import error_perm
import logging
import os
import queue
from queue import Queue
import re
import sys
from threading import Thread
import time
from time import sleep

from deployment.composer import Composer
from deployment.counter import Counter
from deployment.exclusion import Exclusion
from deployment.ftp import Ftp
from deployment.index import Index
from deployment.process import Process
from deployment.purge import Purge
from deployment.scanner import Scanner
from deployment.worker import Worker, WorkersState


class Deployment:
    workers_state = None

    def __init__(self, config):
        self.mapping = {}
        self.extensions = []
        self.workers = []

        self.config = config
        self.counter = Counter()
        self.index = Index(self.config)
        self.ftp = Ftp(self.config)
        self.failed = Queue()

        self.dry_run = False

    def deploy(self, skip_before_and_after, purge_partial_enabled, purge_only_enabled, purge_skip_enabled, force):
        if self.dry_run:
            logging.info("Executing DRY RUN")

        if purge_only_enabled:
            self.purge(purge_partial_enabled)
            return

        remove = True
        contents = {}
        if not force and not self.dry_run:
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
            if skip_before_and_after or self.dry_run:
                logging.info("Skipping before commands")
            else:
                logging.info("Running before commands:")
                self.run_commands(self.config.run_before)

        logging.info("Scanning...")
        exclusion = Exclusion(roots, self.config.ignore, self.mapping)
        scanner = Scanner(self.config, roots, exclusion)
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
                    if path not in objects and not exclusion.is_ignored_relative(path):
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

        if self.dry_run:
            logging.warning("Not uploading index in dry run")
        else:
            logging.info("Uploading index...")
            self.index.upload()
            logging.info("Index uploaded")

        if not purge_skip_enabled:
            self.purge(purge_partial_enabled)

        if len(self.config.run_after) > 0:
            if skip_before_and_after or self.dry_run:
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

    def purge(self, purge_partial_enabled):
        if len(self.config.purge) == 0:
            logging.info("Nothing to purge")
        else:
            if self.dry_run:
                logging.warning("Purge is not available in dry run")
                return

            logging.info("Purging...")

            to_purge = self.config.purge
            extension_count = len(self.extensions)
            if extension_count > 0 and purge_partial_enabled:
                to_purge = []
                for extension in self.extensions:
                    if extension in self.config.purge_partial and self.config.purge_partial[extension] not in to_purge:
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
                        self.ftp.chmod(current, 777)
                    except error_perm:
                        pass

            for base, names in base_folders.items():
                try:
                    objects = self.ftp.list_directory_contents(base)
                    for object in objects:
                        for name in names:
                            if re.search(r"^" + name + r"_[0-9]+\.tmp$", object):
                                to_delete.append(base + "/" + object)
                except error_perm as e:
                    message = str(e)
                    if message.startswith("550"):  # directory not exists
                        continue
                    raise e

            purge = Purge(self.config)
            for path in to_delete:
                purge.add(path)
            directories, files = purge.process()

            logging.info("Purging done, " + str(files) + " files and " + str(directories) + " directories")

    def process_queue(self, item_queue, mode):
        if self.dry_run:
            if mode == "upload":
                mode = "Uploading"
            elif mode == "remove":
                mode = "Removing"

            while True:
                try:
                    path = item_queue.get_nowait()

                    counter = self.counter.counter()
                    logging.info("%s (%s) %s" % (mode, counter, path))
                except queue.Empty:
                    break

            return

        self.workers_state = WorkersState()

        self.workers = []
        for number in range(self.config.threads):
            worker = Worker(
                item_queue, self.config, self.counter, self.index, self.failed, mode, self.mapping, self.workers_state
            )
            worker.start()
            self.workers.append(worker)

        Thread(target=self.monitor, args=(self.workers, item_queue), daemon=True).start()

        with item_queue.all_tasks_done:
            while item_queue.unfinished_tasks and self.workers_state.running:
                try:
                    item_queue.all_tasks_done.wait(0.1)
                except TimeoutError:
                    pass

        if item_queue.unfinished_tasks:
            logging.error("Worker queue failed to process")
            sys.exit(1)

        self.workers_state.stop()
        for worker in self.workers:
            worker.join()

    def monitor(self, workers, queue):
        size = queue.qsize()
        while True:
            if size == queue.qsize():
                parts = []
                for index, worker in enumerate(workers):
                    if worker.running:
                        parts.append(str(index + 1) + " " + str(worker.phase) + " (" + str(worker.local_counter) + ")")

                if len(parts) > 0:
                    logging.info("Workers state: " + ", ".join(parts))

            size = queue.qsize()

            sleep(5)

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
