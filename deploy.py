import logging
from logging import StreamHandler
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
    config = Config()
    config.parse(sys.argv[1])

    start_time = timeit.default_timer()
    logging.info("Deploying configuration with name " + config.name)

    logging.info("Using " + str(config.threads) + " threads")

    deployment = Deployment()
    deployment.deploy()

    elapsed = timeit.default_timer() - start_time
    logging.info("Elapsed time " + str(elapsed) + " seconds")

except ConfigException as e:
    logging.error("Configuration error: " + e.message)
