#!/usr/bin/env python3

import logging
from logging import FileHandler, StreamHandler
import os
import sys
import timeit

from deployment.config import Config, ConfigException
from deployment.deployment import Deployment
from deployment.exceptions import MessageException

if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    console = StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)

    deployment = None
    try:
        fileName = ".ftp-deploy.json"

        if not os.path.isfile(fileName) and len(sys.argv) < 2:
            logging.error("Configuration file " + fileName + " doesn't exist")
            sys.exit(1)
        elif len(sys.argv) > 1:
            fileName = sys.argv[1]

            if not os.path.isfile(fileName):
                fileName = ".ftp-" + sys.argv[1] + ".json"

            if not os.path.isfile(fileName):
                logging.error("Configuration file " + sys.argv[1] + " doesn't exist")
                sys.exit(1)

        config = Config()
        config.parse(fileName)

        if config.file_log:
            file = FileHandler(config.local + "/" + fileName + ".log")
            file.setLevel(logging.INFO)
            file.setFormatter(formatter)
            logger.addHandler(file)

        start_time = timeit.default_timer()
        logging.info("Deploying configuration with name " + config.name)

        logging.info("Using " + str(config.threads) + " threads")

        deployment = Deployment(config)
        deployment.deploy()

        elapsed = timeit.default_timer() - start_time
        logging.info("Elapsed time " + str(elapsed) + " seconds")

        sys.exit(0)

    except MessageException as e:
        logging.error(str(e))
        sys.exit(1)
    finally:
        if deployment is not None:
            deployment.close()
