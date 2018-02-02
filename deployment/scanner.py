from collections import OrderedDict
import hashlib
import logging
import os

from index import Index


class Scanner:
    def __init__(self, config, root, ignored, mode):
        self.config = config
        self.root = root
        self.ignored = self.format_ignored(ignored)
        self.mode = mode

    def scan(self):
        result = {}
        total = 0

        root = self.root
        if os.name == "nt":
            root = root.replace("\\", "/")
        prefix = len(root)

        for folder, subs, files in os.walk(root):
            if folder not in result and folder != root:
                pattern = self.is_ignored(folder)
                if not pattern or pattern == folder:
                    directory = folder[prefix:]
                    if os.name == "nt":
                        directory = directory.replace("\\", "/")
                    result[directory] = None

            for file in files:
                total += 1
                path = os.path.join(folder, file)
                if not self.is_ignored(path):
                    if os.name == "nt":
                        path = path.replace("\\", "/")

                    if self.mode == Index.MODE_SHA256:
                        value = self.calculate_sha256_checksum(path)
                    elif self.mode == Index.MODE_TIME:
                        value = self.get_modify_time(path)
                    else:
                        raise Exception("Unknown mode: " + self.mode)

                    result[path[prefix:]] = value

                    directory = path
                    while True:
                        directory = os.path.dirname(directory)
                        if directory in result:
                            break
                        if directory == root:
                            break
                        result[directory[prefix:]] = None

        logging.info("Found " + str(total) + " objects")

        keys = result.keys()
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = result[key]

        logging.info("Found " + str(len(ordered)) + " valid objects to take care of")

        return ordered

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
