from collections import OrderedDict
import logging
from multiprocessing import Pool, cpu_count, Manager
import os
from queue import Empty

from deployment.checksum import sha256_checksum
from deployment.index import Index


class Scanner:
    def __init__(self, config, roots, ignored, mapping):
        self.config = config
        self.roots = roots
        self.ignored = self.format_ignored(ignored, mapping)
        self.prefix = None
        self.result = {}

    def scan(self):
        scan_queue = Manager().Queue()
        hash_queue = Manager().Queue()
        result_queue = Manager().Queue()

        worker_count = cpu_count()
        scanning_pool = Pool(processes=worker_count)
        hashing_pool = Pool(processes=worker_count)
        for count in range(0, worker_count):
            scanning_pool.apply_async(self.scanning_worker, (scan_queue, hash_queue, result_queue))
            hashing_pool.apply_async(self.hashing_worker, (hash_queue, result_queue))

        for root in self.roots:
            self.prefix = prefix = len(root)
            scan_queue.put((root, prefix))

        scan_queue.join()
        hash_queue.join()

        try:
            for path, value in iter(result_queue.get_nowait, None):
                self.result[path] = value
        except Empty:
            pass

        scanning_pool.terminate()
        hashing_pool.terminate()

        keys = list(self.result.keys())
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = self.result[key]

        logging.info("Found " + str(len(ordered)) + " valid objects to take care of")

        return ordered

    def scanning_worker(self, scan_queue, hash_queue, result_queue):
        while True:
            try:
                parent, prefix = scan_queue.get_nowait()

                with os.scandir(parent) as iterator:
                    for entry in iterator:
                        path = entry.path
                        if os.name == "nt":
                            path = path.replace("\\", "/")

                        ignored = self.is_ignored(path)

                        if entry.is_file():
                            if not ignored:
                                hash_queue.put((path, prefix))
                        else:
                            if not ignored or ignored == path:
                                if ignored != path:
                                    scan_queue.put((path, prefix))
                                result_queue.put((path[prefix:], None))

                scan_queue.task_done()
            except Empty:
                pass

    def hashing_worker(self, hash_queue, result_queue):
        while True:
            try:
                path, prefix = hash_queue.get_nowait()

                hash = sha256_checksum(path, self.config.block_size)
                result_queue.put((path[prefix:], hash))

                hash_queue.task_done()
            except Empty:
                pass

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
