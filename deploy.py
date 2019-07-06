#!/usr/bin/env python3
import argparse
import logging
from logging import FileHandler, StreamHandler
import os
import sys
import timeit

from deployment.config import Config
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

    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="*", help="configuration path or alias")
    parser.add_argument("-s", "--skip", action="store_true", help="skip before commands", default=False)
    parser.add_argument("-pp", "--partial-purge", action="store_true", help="activate partial purge", default=False)
    args = parser.parse_args()

    deployment = None
    try:
        fileName = "deploy"
        if len(args.name) > 0:
            fileName = args.name[0]

        if not os.path.isfile(fileName):
            fileName = ".ftp-" + fileName + ".json"

        if not os.path.isfile(fileName):
            logging.error("Configuration file " + fileName + " doesn't exist")
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
        deployment.deploy(args.skip, args.partial_purge)

        elapsed = timeit.default_timer() - start_time
        logging.info("Elapsed time " + str(elapsed) + " seconds")

        sys.exit(0)

    except MessageException as e:
        logging.error(str(e))
        sys.exit(1)
    finally:
        if deployment is not None:
            deployment.close()
