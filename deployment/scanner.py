from collections import OrderedDict
import os

import logging


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
            for file in files:
                total += 1
                path = os.path.join(folder, file)
                if not self.is_ignored(path):
                    if os.name == "nt":
                        path = path.replace("\\", "/")
                        result[path[prefix:]] = str(os.path.getmtime(path))

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
        formatted = []
        for pattern in ignored:
            if os.name == "nt":
                pattern = pattern.replace("/", "\\")
            formatted.append(pattern)
        return formatted

    def is_ignored(self, path):
        for pattern in self.ignored:
            if pattern.startswith("/") and path.startswith(pattern):
                return True
            elif pattern in path:
                return True

        return False
