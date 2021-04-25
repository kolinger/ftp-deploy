#!/usr/bin/env python3
try:
    import argparse
    import logging
    from logging import FileHandler, StreamHandler
    import os
    import sys
    import timeit

    from deployment.config import Config
    from deployment.deployment import Deployment
    from deployment.exceptions import MessageException
    from deployment.composer import Composer

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
        parser.add_argument("-s", "--skip", action="store_true", help="skip before and after commands", default=False)
        parser.add_argument("-pp", "--purge-partial", action="store_true", help="activate partial purge", default=False)
        parser.add_argument("-po", "--purge-only", action="store_true", help="only purge", default=False)
        parser.add_argument("-ps", "--purge-skip", action="store_true", help="skip purge", default=False)
        parser.add_argument("-t", "--threads", help="override config threads", default=None, type=int)
        parser.add_argument("-pt", "--purge-threads", help="override config threads", default=None, type=int)
        parser.add_argument("-b", "--bind", help="bind interface or source address", default=None)
        parser.add_argument("-f", "--force", action="store_true", help="force whole upload", default=False)
        parser.add_argument("--dry-run", action="store_true", help="just report changes", default=False)
        parser.add_argument("--clear-composer", action="store_true", help="clear composer and exit", default=False)
        args = parser.parse_args()

        deployment = None
        config = None
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

            if args.threads is not None:
                config.threads = args.threads

            if args.purge_threads is not None:
                config.purge_threads = args.purge_threads

            if args.bind is not None:
                config.bind = args.bind

            if config.file_log:
                file = FileHandler(config.local + "/" + fileName + ".log")
                file.setLevel(logging.INFO)
                file.setFormatter(formatter)
                logger.addHandler(file)

            if args.clear_composer:
                logging.info("Clearing temporary composer directory")
                Composer(config).clear()
                logging.info("Done")
                sys.exit(0)

            start_time = timeit.default_timer()
            logging.info("Deploying configuration with name " + config.name)

            logging.info("Using " + str(config.threads) + " threads")

            deployment = Deployment(config)
            deployment.dry_run = args.dry_run
            deployment.deploy(args.skip, args.purge_partial, args.purge_only, args.purge_skip, args.force)

            elapsed = timeit.default_timer() - start_time
            logging.info("Elapsed time " + str(elapsed) + " seconds")

            sys.exit(0)

        except MessageException as e:
            logging.error(str(e))
            sys.exit(1)
        except SystemExit as e:
            if e.code != 0:
                logging.critical("Terminated with code %s" % e.code)
        except KeyboardInterrupt:
            if config and deployment:
                index_path = config.local + deployment.index.FILE_NAME
                if os.path.exists(index_path):
                    deployment.index.close()
                    os.remove(index_path)
            logging.critical("Terminated by user")
            sys.exit(1)
        except:
            logging.exception(sys.exc_info()[0])
            sys.exit(1)
        finally:
            if deployment is not None:
                deployment.close()

except (KeyboardInterrupt, SystemExit):
    exit(1)
