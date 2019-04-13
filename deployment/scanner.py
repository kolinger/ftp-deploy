from collections import OrderedDict
import logging
from multiprocessing import Pool, cpu_count
import os

from deployment.checksum import sha256_checksum
from deployment.index import Index


def process(path, block_size):
    return [path, sha256_checksum(path, block_size)]


class Scanner:
    def __init__(self, config, roots, ignored, mapping):
        self.config = config
        self.roots = roots
        self.ignored = self.format_ignored(ignored, mapping)
        self.prefix = None
        self.result = {}

    def scan(self):
        total = 0

        pool = Pool(processes=cpu_count())

        for root in self.roots:
            self.prefix = prefix = len(root)

            waiting_room = []
            for base, directories, files in os.walk(root):
                if os.name == "nt":
                    base = base.replace("\\", "/")

                for directory in directories:
                    path = os.path.join(base, directory)
                    pattern = self.is_ignored(path)
                    if pattern:
                        if pattern == path:
                            self.result[base[prefix:]] = None
                        directories.remove(directory)

                if base not in self.result and base != root:
                    pattern = self.is_ignored(base)
                    if not pattern or pattern == base:
                        self.result[base[prefix:]] = None
                        total += 1
                    if pattern:
                        continue

                for file in files:
                    total += 1

                    path = os.path.join(base, file)
                    if os.name == "nt":
                        path = path.replace("\\", "/")

                    if not self.is_ignored(path):
                        result = pool.apply_async(process, args=(path, self.config.block_size))
                        waiting_room.append(result)

                        directory = path
                        while True:
                            directory = os.path.dirname(directory)
                            if directory in self.result:
                                break
                            if directory == root:
                                break
                            self.result[directory[prefix:]] = None

            for result in waiting_room:
                result = result.get(3600)
                path = result[0]
                value = result[1]
                self.result[path[self.prefix:]] = value

        pool.close()
        pool.join()

        logging.info("Found " + str(total) + " objects")

        keys = list(self.result.keys())
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = self.result[key]

        logging.info("Found " + str(len(ordered)) + " valid objects to take care of")

        return ordered

    def format_ignored(self, ignored, mapping):
        ignored.append(Index.FILE_NAME)
        ignored.append(Index.BACKUP_FILE_NAME)
        ignored.append("/.ftp-")

        formatted = []
        for pattern in ignored:
            if pattern in mapping:
                for root in self.roots:
                    if not mapping[pattern].startswith(root):
                        formatted.append(root + pattern)

            elif pattern.startswith("/"):
                for root in self.roots:
                    formatted.append(root + pattern)

            else:
                formatted.append(pattern)

        return formatted

    def is_ignored(self, path):
        for pattern in self.ignored:
            if pattern.startswith("/") and path.startswith(pattern):
                return pattern
            elif pattern in path:
                return pattern

        return False
