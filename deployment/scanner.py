from collections import OrderedDict
import hashlib
import logging
from multiprocessing.pool import ThreadPool
import os

from index import Index


class Scanner:
    def __init__(self, config, root, ignored):
        self.config = config
        self.root = root
        self.ignored = self.format_ignored(ignored)
        self.prefix = None
        self.result = {}

    def scan(self):
        total = 0

        root = self.root
        if os.name == "nt":
            root = root.replace("\\", "/")
        self.prefix = prefix = len(root)

        pool = ThreadPool(processes=self.config.threads)

        for folder, subs, files in os.walk(root):
            if folder not in self.result and folder != root:
                pattern = self.is_ignored(folder)
                if not pattern or pattern == folder:
                    directory = folder[prefix:]
                    if os.name == "nt":
                        directory = directory.replace("\\", "/")
                    self.result[directory] = None

            for file in files:
                total += 1
                path = os.path.join(folder, file)
                if not self.is_ignored(path):
                    if os.name == "nt":
                        path = path.replace("\\", "/")

                        pool.apply_async(self.process, args=(path,))

                    directory = path
                    while True:
                        directory = os.path.dirname(directory)
                        if directory in self.result:
                            break
                        if directory == root:
                            break
                        self.result[directory[prefix:]] = None

        pool.close()
        pool.join()

        logging.info("Found " + str(total) + " objects")

        keys = self.result.keys()
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = self.result[key]

        logging.info("Found " + str(len(ordered)) + " valid objects to take care of")

        return ordered

    def process(self, path):
        value = self.calculate_sha256_checksum(path)
        self.result[path[self.prefix:]] = value

    def get_modify_time(self, path):
        return str(int(os.path.getmtime(path)))

    def calculate_sha256_checksum(self, path):
        hash = hashlib.sha256()
        with open(path, "rb") as file:
            for block in iter(lambda: file.read(self.config.block_size), b''):
                hash.update(block)
        return hash.hexdigest()

    def format_ignored(self, ignored):
        ignored.append(Index.FILE_NAME)
        ignored.append(Index.BACKUP_FILE_NAME)
        ignored.append("/.ftp-")

        formatted = []
        for pattern in ignored:
            if pattern.startswith("/"):
                formatted.append(self.root + pattern)
            if os.name == "nt":
                pattern = pattern.replace("/", "\\")
            formatted.append(pattern)

        return formatted

    def is_ignored(self, path):
        for pattern in self.ignored:
            if (pattern.startswith("/") or pattern.startswith("\\")) and path.startswith(pattern):
                return pattern
            elif pattern in path:
                return pattern

        return False
