import logging
import os
import shutil

from deployment.checksum import sha256_checksum
from deployment.process import Process


class Composer:
    def __init__(self, config):
        self.config = config

    def process(self):
        logging.info("Processing composer")

        root = self.config.local.rstrip("/")
        prefix = os.path.dirname(self.config.composer)
        configuration = root + "/" + self.config.composer
        lock = configuration.replace(".json", ".lock")

        temporary = root + "/../.ftp-deploy/" + os.path.basename(root) + "/" + prefix
        temporary = os.path.realpath(temporary)
        os.makedirs(temporary, exist_ok=True)

        if os.path.exists(lock):
            previous_lock = temporary + "/composer.lock"
            if os.path.exists(previous_lock):
                checksum = sha256_checksum(lock)
                previous_checksum = sha256_checksum(previous_lock)
                if checksum == previous_checksum:
                    logging.info("Composer is up to date, skipping")
                    return "/" + prefix + "/vendor", temporary + "/vendor"

            shutil.copy(lock, temporary + "/composer.lock")

        if not os.path.exists(configuration):
            logging.error("Composer configuration " + configuration + " not found")
            exit(1)

        shutil.copyfile(configuration, temporary + "/composer.json")

        command = [
            "composer",
            "install",
            "--no-dev",
            "--prefer-dist",
            "--no-suggest",
            "--no-progress",
            "--ignore-platform-reqs",
            "--no-interaction",
            "--working-dir",
            temporary
        ]
        process = Process(" ".join(command)).execute()
        if process.return_code() != 0:
            logging.error("Composer failed with output: " + process.read())
            exit(1)

        return "/" + prefix + "/vendor", temporary + "/vendor"
