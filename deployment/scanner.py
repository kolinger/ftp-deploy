from collections import OrderedDict
import logging
from logging import StreamHandler
import multiprocessing
from multiprocessing import Pool, cpu_count, Manager
import os
from os import DirEntry
from queue import Empty
import re
import signal
import sys
from time import sleep, time

from deployment.checksum import sha256_checksum


class Scanner:
    def __init__(self, config, roots, exclusion):
        self.config = config
        self.roots = roots
        self.exclusion = exclusion
        self.prefix = None
        self.result = {}

    def scan(self):
        scan_queue = Manager().Queue()
        hash_queue = Manager().Queue()
        result_queue = Manager().Queue()
        running = Manager().Value(bool, True)
        running_count = Manager().Value(int, 0)

        scanning_pool = None
        hashing_pool = None

        try:
            worker_count = cpu_count()
            original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
            scanning_pool = Pool(processes=worker_count, initializer=setup_logging)
            hashing_pool = Pool(processes=worker_count, initializer=setup_logging)
            signal.signal(signal.SIGINT, original_sigint_handler)
            for count in range(0, worker_count):
                scanning_pool.apply_async(self.scanning_worker, (
                    running, running_count, scan_queue, hash_queue, result_queue
                ))
                hashing_pool.apply_async(self.hashing_worker, (
                    running, running_count, hash_queue, result_queue
                ))

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
        finally:
            running.set(False)
            deadline = time() + 10
            while running_count.get() > 0 and deadline < time():
                sleep(0.1)
            if running_count.get() > 0:
                scanning_pool.terminate()
                hashing_pool.terminate()

        keys = list(self.result.keys())
        keys.sort()

        ordered = OrderedDict()
        for key in keys:
            ordered[key] = self.result[key]

        logging.info("Found " + str(len(ordered)) + " valid objects to take care of")

        return ordered

    def scanning_worker(self, running, running_count, scan_queue, hash_queue, result_queue):
        running_count.set(running_count.get() + 1)

        try:
            while running.get():
                try:
                    parent, prefix = scan_queue.get_nowait()

                    with os.scandir(parent) as iterator:
                        iterator = iterator  # type: list[DirEntry]
                        for entry in iterator:
                            path = entry.path
                            if os.name == "nt":
                                path = path.replace("\\", "/")

                            ignored = self.exclusion.is_ignored_absolute(path)

                            if entry.is_file():
                                if not ignored:
                                    hash_queue.put((path, prefix))
                            else:
                                if isinstance(ignored, re.Pattern):
                                    direct_ignored = ignored.search(path)
                                else:
                                    direct_ignored = ignored == path

                                if not ignored or direct_ignored:
                                    if not direct_ignored:
                                        scan_queue.put((path, prefix))

                                    if not ignored or not direct_ignored:
                                        result_queue.put((path[prefix:], None))

                    scan_queue.task_done()
                except Empty:
                    pass

        except (KeyboardInterrupt, SystemExit):
            pass
        except:
            logging.exception(sys.exc_info()[0])

        running_count.set(running_count.get() - 1)

    def hashing_worker(self, running, running_count, hash_queue, result_queue):
        running_count.set(running_count.get() + 1)

        try:
            while running.get():
                try:
                    path, prefix = hash_queue.get_nowait()

                    hash = sha256_checksum(path, self.config.block_size)
                    result_queue.put((path[prefix:], hash))

                    hash_queue.task_done()
                except Empty:
                    pass

        except (KeyboardInterrupt, SystemExit):
            pass
        except:
            logging.exception(sys.exc_info()[0])

        running_count.set(running_count.get() - 1)


def setup_logging():
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    logger = multiprocessing.get_logger()
    logger.setLevel(logging.ERROR)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    console = StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)
