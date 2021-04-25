import logging
import os
import shutil
import sys

from deployment.checksum import sha256_checksum
from deployment.process import Process


class Composer:
    temporary_lock = None
    temporary_json = None

    def __init__(self, config):
        self.config = config

        self.root = self.config.local.rstrip("/")
        self.prefix = os.path.dirname(self.config.composer)
        self.configuration = self.root + "/" + self.config.composer
        self.lock = self.configuration.replace(".json", ".lock")
        self.temporary = self.root + "/../.ftp-deploy/" + os.path.basename(self.root) + "/" + self.prefix

    def process(self):
        logging.info("Processing composer")

        temporary = os.path.realpath(self.temporary).replace("\\", "/")
        os.makedirs(temporary, exist_ok=True)

        self.temporary_lock = temporary + "/composer.lock"
        self.temporary_json = temporary + "/composer.json"

        try:
            if os.path.exists(self.lock):
                if os.path.exists(self.temporary_lock):
                    checksum = sha256_checksum(self.lock)
                    previous_checksum = sha256_checksum(self.temporary_lock)
                    if checksum == previous_checksum:
                        logging.info("Composer is up to date, skipping")
                        return "/" + self.prefix + "/vendor", temporary + "/vendor"

                shutil.copy(self.lock, self.temporary_lock)

            if not os.path.exists(self.configuration):
                logging.error("Composer configuration " + self.configuration + " not found")
                self.cleanup()
                sys.exit(1)

            shutil.copyfile(self.configuration, self.temporary_json)

            def output_callback(line):
                logging.info("composer: " + line)

            command = [
                "composer",
                "install",
                "--no-dev",
                "--prefer-dist",
                "--no-progress",
                "--ignore-platform-reqs",
                "--no-interaction",
                "--working-dir",
                temporary
            ]

            if os.name == "nt":
                command.extend(["&", "exit"])  # exit code fix

            process = Process(" ".join(command)).execute(None, output_callback)
            if process.return_code() != 0:
                logging.error("Composer failed with return code: " + str(process.return_code()))
                self.cleanup()
                sys.exit(1)

        except:
            self.cleanup()
            raise

        return "/" + self.prefix + "/vendor", temporary + "/vendor"

    def cleanup(self):
        if os.path.exists(self.temporary_lock):
            os.remove(self.temporary_lock)

        if os.path.exists(self.temporary_json):
            os.remove(self.temporary_json)

    def clear(self):
        shutil.rmtree(os.path.dirname(self.temporary))
