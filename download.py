#!/usr/bin/env python3
import shlex
import subprocess
from time import sleep

try:
    import argparse
    import logging
    from logging import FileHandler, StreamHandler
    import os
    import sys
    from timeit import default_timer as timer

    from deployment.config import Config
    from deployment.deployment import Deployment
    from deployment.exceptions import MessageException


    def mirror(config, force):
        parameters = ""
        for path in config.ignore:
            parameters += " --exclude " + path

        execute = [
            "set net:timeout 30",
            "set net:max-retries 5",
        ]

        if config.bind:
            execute.append("set net:socket-bind-ipv4 " + config.bind)

        if config.secure:
            execute.append("set ssl:verify-certificate false")
        else:
            execute.append("set ftp:ssl-allow false")

        mirror_extra = "--continue" if not force else ""
        execute.extend([
            "open %s:%s" % (config.host, config.port),
            "user " + shlex.quote(config.user) + " " + shlex.quote(config.password),
            "mirror %s --delete --parallel=%s %s %s" % (
                mirror_extra, config.threads, parameters, config.remote
            ),
            "bye",
        ])

        command = [
            "cd " + config.local,
            "wsl lftp -e \"" + " && ".join(execute) + "\"",
        ]
        command = " & ".join(command)

        process = subprocess.Popen(command, shell=True, stderr=sys.stderr, stdout=sys.stdout)
        while process.poll() is None:
            sleep(1)

        if process.returncode != 0:
            logging.error("lftp mirror failed with code: %s" % process.returncode)
            exit(1)

        logging.info("Completed")


    if __name__ == "__main__":
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        console = StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        logger.addHandler(console)

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--help", action="help")
        parser.add_argument("-h", "--host", help="FTP host (port can be specified with colon)", required=True)
        parser.add_argument("-u", "--user", help="FTP user", required=True)
        parser.add_argument("-p", "--password", help="FTP password", default=None)
        parser.add_argument("--insecure", help="Disable TLS", action="store_true", default=False)
        # parser.add_argument("--implicit", help="FTP TLS implicit mode", action="store_true", default=False)
        # parser.add_argument("--active", help="FTP active mode", action="store_true", default=False)
        # parser.add_argument("--passive-workaround", help="FTP passive workaround", action="store_true", default=False)
        parser.add_argument("-t", "--threads", help="Threads count", type=int, default=10)
        parser.add_argument("-b", "--bind", help="Local address to bind to", default=None)
        parser.add_argument("-r", "--remote", help="Remote directory", default="/")
        parser.add_argument("-l", "--local", help="Local directory", default=".")
        parser.add_argument("-i", "--ignore", help="Ignore pattern", action="append")
        parser.add_argument("-f", "--force", help="Force whole transfer", action="store_true", default=False)
        args = parser.parse_args()

        downloader = None
        try:
            config = Config()

            config.host = args.host
            if ":" in args.host:
                host, port = args.host.split(":")
                try:
                    config.port = int(port)
                    config.host = host
                except ValueError:
                    config.host = args.host

            config.user = args.user

            if args.password is not None:
                config.password = args.password
            else:
                config.password = input("Password: ")

            config.secure = not args.insecure
            # config.implicit = args.implicit
            # config.passive = not args.active
            # config.passive_workaround = args.passive_workaround
            config.threads = args.threads
            config.bind = args.bind

            config.remote = args.remote
            config.local = args.local if args.local != "." else os.getcwd()

            if args.ignore:
                config.ignore = args.ignore

            start_time = timer()
            logging.info("Downloading %s@%s%s" % (config.user, config.host, config.remote))
            logging.info("Using %s threads" % config.threads)

            mirror(config, force=args.force)

            logging.info("Elapsed time %s seconds" % (timer() - start_time))

            sys.exit(0)

        except MessageException as e:
            logging.error(str(e))
            sys.exit(1)
        except SystemExit as e:
            if e.code != 0:
                logging.critical("Terminated with code %s" % e.code)
        except KeyboardInterrupt:
            logging.critical("Terminated by user")
            sys.exit(1)
        except:
            logging.exception(sys.exc_info()[0])
            sys.exit(1)

except (KeyboardInterrupt, SystemExit):
    exit(1)
