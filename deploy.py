#!/usr/bin/env python
  
import logging
from logging import StreamHandler
import os
import sys
import timeit

from deployment.config import Config, ConfigException
from deployment.deployment import Deployment

reload(sys)
sys.setdefaultencoding('utf8')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

console = StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(formatter)
logger.addHandler(console)

try:
    name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    fileName = '.' + name + '.json'

    if not os.path.isfile(fileName) and len(sys.argv) < 2:
        logging.error("Configuration file is not provided.")
        sys.exit(1)
    elif len(sys.argv) > 1:
        if os.path.isfile(sys.argv[1]):
            fileName = sys.argv[1]
        else:
            logging.error("Configuration file doesn't exist.")
            sys.exit(1)

    config = Config()
    config.parse(fileName)

    start_time = timeit.default_timer()
    logging.info("Deploying configuration with name " + config.name)

    logging.info("Using " + str(config.threads) + " threads")

    deployment = Deployment()
    deployment.deploy()

    elapsed = timeit.default_timer() - start_time
    logging.info("Elapsed time " + str(elapsed) + " seconds")

    sys.exit(0)

except ConfigException as e:
    logging.error("Configuration error: " + e.message)
    sys.exit(1)
