from collections import OrderedDict
import logging
import os

from index import Index


class Scanner:
    root = None
    ignored = None

    def __init__(self, root, ignored):
        self.root = root
        self.ignored = self.format_ignored(ignored)

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

                    result[path[prefix:]] = str(int(os.path.getmtime(path)))

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

    def format_ignored(self, ignored):
        ignored.append(Index.FILE_NAME)
        ignored.append(Index.BACKUP_FILE_NAME)

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
