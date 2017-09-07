from Queue import Queue
from collections import OrderedDict
from ftplib import error_perm
import logging
import os
import subprocess
import sys

from config import Config
from counter import Counter
from ftp import Ftp
from index import Index
from uploadworker import UploadWorker


class Deployment:
    HASH_DEEP_BINARY = ["tigerdeep64", "-s", "-r"]
    HASH_DEEP_BINARY_FALLBACK = ["tigerdeep", "-s", "-r"]

    def __init__(self):
        self.config = Config()
        self.counter = Counter()
        self.index = Index()
        self.ftp = Ftp()
        self.queue = Queue()

    def deploy(self):
        logging.info("Scanning...")
        self.index.hashes = objects = self.scan(self.config.local)

        logging.info("Found " + str(len(objects)) + " objects")

        valid = []
        printed = []
        for path in objects:
            if self.is_ignored(path):
                process = True

                if len(printed) > 0:
                    for printedPath in printed:
                        if path.startswith(printedPath):
                            process = False
                            break

                if process:
                    printed.append(path)
                    logging.info("Ignoring " + path)
            else:
                valid.append(path)

        logging.info("Found " + str(len(valid)) + " valid objects to take care of")

        logging.info("Calculating changes...")
        to_delete = []

        result = self.index.read()
        remove = result['remove']
        contents = result['contents']

        offset = 0
        if contents is None:
            for path in valid:
                self.queue.put(path)
        else:
            result = self.parse(contents, False)
            for path in valid:
                hash = objects[path]
                if path in result and (hash is None or hash == result[path]):
                    self.index.write(path)
                else:
                    self.queue.put(path)

            if os.path.isfile(self.index.backup_path):
                os.remove(self.index.backup_path)

            if remove:
                for path in result:
                    if path not in valid:
                        to_delete.append(path)
            else:
                offset = len(result)

        self.counter.total = str(self.queue.qsize() + offset)
        self.counter.count = 1 + offset

        for number in range(self.config.threads):
            worker = UploadWorker(self.queue)
            worker.start()

        self.queue.join()

        logging.info("Uploading done")

        for path in reversed(to_delete):
            try:
                logging.info("Removing " + path)
                self.ftp.delete_file_or_directory(self.config.remote + path)
            except error_perm as e:
                logging.exception(e)

        logging.info("Removing done")

        self.index.upload()

        logging.info("Index uploaded")

        self.purge()

        self.ftp.close()

    def purge(self):
        for path in self.config.purge:
            try:
                # config = Config()
                # ftp = FTPHost(self.ftp)
                # for dirname, subdirs, files in ftp.walk(config.remote + path):
                #     print dirname, "has file(s)", ", ".join(files)
                # self.ftp.list_directory_contents(self.config.remote + path, self.spam)
                self.ftp.delete_recursive(self.config.remote + path)
            except error_perm as e:
                pass

    def spam(self, path):
        print path

    def scan(self, directory):
        command = []

        try:
            command = self.HASH_DEEP_BINARY
            if self.config.hashdeep_fs_mode:
                command.append("-F" + self.config.hashdeep_fs_mode)
            command.append(directory)
            output = self.run_command(command)
        except:
            try:
                command = self.HASH_DEEP_BINARY_FALLBACK
                if self.config.hashdeep_fs_mode:
                    command.append("-F" + self.config.hashdeep_fs_mode)
                command.append(directory)
                output = self.run_command(command)
            except OSError as e:
                logging.error("Can't execute hashdeep binary, command: " + str(command) + ", reason: " + str(e))
                sys.exit(1)

        return self.parse(output)

    def is_ignored(self, path):
        for pattern in self.config.ignore:
            if pattern.startswith("/") and path.startswith(pattern):
                return True
            elif pattern in path:
                return True

        return False

    def parse(self, output, raw=True):
        root = os.path.realpath(self.config.local)
        length = len(root)

        result = {}
        for line in output:
            parts = line.split(" ", 1)

            if len(parts) != 2:
                continue

            hash = parts[0].strip()
            path = parts[1].strip()

            if raw:
                path = os.path.realpath(path)
                path = path[length:].replace("\\", "/")

                directory = path
                while True:
                    directory = os.path.dirname(directory)
                    if directory in result:
                        break
                    if directory == "/":
                        break
                    result[directory] = None

            if hash == "None":
                hash = None

            result[path] = hash

        keys = result.keys()
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = result[key]

        return ordered

    def run_command(self, command):
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return iter(process.stdout.readline, b"")
