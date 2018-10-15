import logging
import os
import shutil

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
            current_time = int(os.path.getmtime(lock))
            lock_time = temporary + "/lock.time"
            if os.path.exists(lock_time):
                with open(lock_time, "r") as file:
                    try:
                        time = int(file.read())
                    except ValueError:
                        time = 0
                if current_time == time:
                    logging.info("Composer is up to date, skipping")
                    return "/" + prefix + "/vendor", temporary + "/vendor"

            shutil.copy(lock, temporary + "/composer.lock")
            with open(lock_time, "w") as file:
                file.write(str(current_time))

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
