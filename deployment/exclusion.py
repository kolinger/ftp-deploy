import re

from deployment.index import Index


class Exclusion:
    def __init__(self, roots, ignored, mapping):
        self.roots = roots
        self.patterns = self.init(ignored, mapping)

    def init(self, ignored, mapping):
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

        analyzed = []
        for pattern in formatted:
            kind = None
            if "*" in pattern:
                pieces = pattern.split("*")
                pieces = list(map(re.escape, pieces))
                pattern = ".*".join(pieces)
                pattern = re.compile("^" + pattern + r"$", flags=re.I | re.DOTALL)
                kind = "regex"
            elif pattern.startswith("/") or re.match(r"^[a-z]+:/", pattern, flags=re.I) is not None:
                kind = "root"

            analyzed.append((kind, pattern))

        return analyzed

    def is_ignored_absolute(self, path):
        for kind, pattern in self.patterns:
            if kind == "regex":
                if pattern.search(path):
                    return pattern

            elif kind == "root":
                if path.startswith(pattern):
                    return pattern

            elif pattern in path:
                return pattern

        return False

    def is_ignored_relative(self, path):
        for root in self.roots:
            if self.is_ignored_absolute(root + path):
                return True
        return False
