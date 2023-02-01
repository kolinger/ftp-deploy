#!/usr/bin/env python3
import argparse
from getpass import getpass
import logging
from logging import StreamHandler
import os
import platform
import shlex
import subprocess
import sys
from timeit import default_timer as timer

from deployment.config import Config
from deployment.exceptions import MessageException

known_operations = [
    "Finished mirror",
    "Finished transfer",
    "Transferring file",
    "Removing old file",
    "Making directory",
    "Removing old directory",
]


def mirror(config, force, lftp_binary):
    parameters = "-vv"
    for path in config.ignore:
        parameters += " --exclude %s" % path
    if force:
        parameters += " --continue"

    execute = [
        "set net:connection-limit %s" % config.threads,
        "set net:timeout 30",
        "set net:max-retries 20",
        "set dns:order \\\"inet inet6\\\"",
        "set mirror:parallel-directories true",
    ]

    error_wait = config.connection_limit_wait
    if error_wait > 0:
        execute.append("set net:reconnect-interval-base %s" % error_wait)
        execute.append("set net:reconnect-interval-max %s" % error_wait)
        execute.append("set net:reconnect-interval-multiplier 1")

    if config.bind:
        execute.append("set net:socket-bind-ipv4 %s" % config.bind)

    if config.secure:
        execute.append("set ssl:verify-certificate false")
    else:
        execute.append("set ftp:ssl-allow false")

    execute.extend([
        "open %s:%s" % (config.host, config.port),
        "user %s %s" % (shlex.quote(config.user), shlex.quote(config.password)),
        "mirror --delete --parallel=%s %s %s" % (
            config.threads, parameters, config.remote
        ),
        "echo done",
    ])

    if platform.system() == "Windows":
        lftp_binary = "wsl.exe %s" % lftp_binary

    command = [
        "cd %s" % config.local,
        "%s -c \"%s\"" % (lftp_binary, " && ".join(execute)),
    ]
    command = " && ".join(command)

    lines = []
    process = subprocess.Popen(command, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    while process.poll() is None:
        for line in process.stdout:
            line = line.decode("utf-8", errors="ignore").rstrip()
            print(line)
            lines.append(line)

    unexpected = []
    expected = 0
    found_done = False
    for line in lines:
        is_known = False
        for known in known_operations:
            if line.startswith(known):
                is_known = True
                break

        if is_known:
            expected += 1
        else:
            if line == "done":
                found_done = True
            else:
                unexpected.append(line)

    if process.returncode != 0:
        safe = command.replace(config.password, "****")
        logging.error("lftp mirror failed with command: %s, exit code: %s, unexpected output: %s" % (
            safe, process.returncode, "\n".join(unexpected)
        ))
        exit(1)

    if (len(unexpected) > 0 or expected == 0) and found_done:
        safe = command.replace(config.password, "****")
        logging.error("lftp mirror returned unexpected output with command: %s, unexpected output: %s" % (
            safe, "\n".join(unexpected)
        ))
        exit(1)

    logging.info("Completed")


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    console = StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--help", action="help")
        parser.add_argument("-h", "--host", help="FTP host (port can be specified with colon)", required=True)
        parser.add_argument("-u", "--user", help="FTP user", required=True)
        parser.add_argument("-p", "--password", help="FTP password", default=None)
        parser.add_argument("--insecure", help="Disable TLS", action="store_true", default=False)
        # parser.add_argument("--implicit", help="FTP TLS implicit mode", action="store_true", default=False)
        # parser.add_argument("--active", help="FTP active mode", action="store_true", default=False)
        # parser.add_argument("--passive-workaround", help="FTP passive workaround", action="store_true", default=False)
        parser.add_argument("--error-wait", help="Wait given seconds on error", type=int, default=10)
        parser.add_argument("-t", "--threads", help="Threads count", type=int, default=10)
        parser.add_argument("-b", "--bind", help="Local address to bind to", default=None)
        parser.add_argument("-r", "--remote", help="Remote directory", default="/")
        parser.add_argument("-l", "--local", help="Local directory", default=".")
        parser.add_argument("-i", "--ignore", help="Ignore pattern", action="append")
        parser.add_argument("-f", "--force", help="Force whole transfer", action="store_true", default=False)
        parser.add_argument("--lftp-binary", help="lftp binary path", default="/usr/bin/lftp")
        args = parser.parse_args()

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
            config.password = getpass("Password: ")

        config.secure = not args.insecure
        # config.implicit = args.implicit
        # config.passive = not args.active
        # config.passive_workaround = args.passive_workaround
        config.connection_limit_wait = args.error_wait
        config.threads = args.threads
        config.bind = args.bind

        config.remote = args.remote
        config.local = args.local if args.local != "." else os.getcwd()

        if args.ignore:
            config.ignore = args.ignore

        start_time = timer()
        logging.info("Downloading %s@%s%s" % (config.user, config.host, config.remote))
        logging.info("Using %s threads" % config.threads)

        mirror(config, force=args.force, lftp_binary=args.lftp_binary)

        elapsed = round((timer() - start_time) * 1000) / 1000
        logging.info("Elapsed %s seconds" % elapsed)

        exit(0)

    except MessageException as e:
        logging.error(str(e))
        exit(1)
    except SystemExit as e:
        if e.code != 0:
            logging.critical("Terminated with code %s" % e.code)
            exit(e.code)
    except KeyboardInterrupt:
        logging.critical("Terminated by user")
        exit(1)
    except:
        logging.exception(sys.exc_info()[0])
        exit(1)
