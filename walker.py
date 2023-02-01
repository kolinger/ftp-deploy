#!/usr/bin/env python3
import argparse
from getpass import getpass
import logging
from logging import StreamHandler
import os.path
import re
import sys
from timeit import default_timer as timer

from deployment import encryption
from deployment.config import Config
from deployment.exceptions import MessageException, ConfigException


def find_configs(directory, pattern, excluded):
    if not os.path.exists(directory):
        raise MessageException("Directory '%s' doesn't exist" % directory)

    pattern = re.compile(pattern, flags=re.I)

    found = []
    total = 0
    for parent, directories, files in os.walk(directory):
        for directory_name in directories:
            if directory_name in excluded:
                directories.remove(directory_name)

        for file_name in files:
            total += 1
            if pattern.search(file_name):
                path = os.path.join(parent, file_name)
                found.append(path)

    return found, total


def walk(action, directory, pattern, excluded, dry_run):
    if dry_run:
        logging.info("Executing DRY RUN")

    logging.info("Searching for configs... This may take a while...")
    found, total = find_configs(directory, pattern, excluded)
    logging.info("Found %s config(s) out of %s files" % (len(found), total))

    if action == "encrypt":
        logging.info("Encryption started...")
    else:
        logging.info("Decryption started...")

    passphrase = getpass("Passphrase: ")

    warnings = []
    verified = False
    success = 0
    invalid = 0
    skipped = 0
    for path in found:
        try:
            config = Config()
            config.parse(path)

            if action == "encrypt":
                if config.password is None and config.password_encrypted is not None:
                    logging.info("Config '%s' is already encrypted" % path)
                    skipped += 1
                    continue

                if config.password is None or config.password == "":
                    logging.info("Config '%s' has empty password, there is nothing to encrypt" % path)
                    skipped += 1
                    continue

                encryption.encrypt_config_password(config, passphrase, verified)
                if not dry_run:
                    encryption.save_encrypted_password(config)
                    logging.info("Config '%s' was successfully encrypted" % path)
                else:
                    logging.info("Config '%s' would be successfully encrypted" % path)

                success += 1
                verified = True
            else:
                if config.password_encrypted is None:
                    logging.info("Config '%s' is already decrypted" % path)
                    skipped += 1
                    continue

                encryption.decrypt_config_password(config, passphrase)
                if not dry_run:
                    encryption.save_decrypted_password(config)
                    logging.info("Config '%s' was successfully decrypted" % path)
                else:
                    logging.info("Config '%s' would be successfully decrypted" % path)

                success += 1

        except ConfigException:
            logging.warning("Config '%s' wasn't processed since it doesn't look like valid ftp-deploy config" % path)
            warnings.append(path)
            invalid += 1

    logging.info("Results: %s total, %s successful, %s invalid, %s skipped" % (len(found), success, invalid, skipped))

    if dry_run:
        if action == "encrypt":
            logging.info("Dry run - all passwords were left as plaintext")
        else:
            logging.info("Dry run - all passwords were left encrypted")

    if len(warnings) > 0:
        lines = "\n".join(warnings)
        logging.warning(
            "While processing directory '%s' following files were matched but have invalid contents:\n%s" % (
                directory, lines
            )
        )

        return 1

    return 0


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    console = StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("action", nargs="?", help="what to do? (encrypt, decrypt)")
        parser.add_argument("--help", action="help")
        parser.add_argument("--directory", help="directory to scan (default: current working directory)")
        parser.add_argument("--exclude", help="directory to exclude (default: .git,.idea,vendor)")
        pattern_default = r"^\.ftp-.+\.json$"
        pattern_help = "regex pattern for matching ftp-deploy config files (default: %s)" % pattern_default
        parser.add_argument("--pattern", help=pattern_help)
        parser.add_argument("--dry-run", action="store_true", help="don't save changes", default=False)
        args = parser.parse_args()

        if args.action not in ["encrypt", "decrypt"]:
            logging.error("First argument is missing\nProvide ACTION: encrypt or decrypt")
            sys.exit(0)

        excluded = args.exclude
        if excluded is None:
            excluded = ".git,.idea,vendor"
        pieces = []
        for piece in excluded.split(","):
            piece = piece.strip()
            if piece == "":
                continue
            pieces.append(piece)
        excluded = pieces

        start_time = timer()

        pattern = args.pattern if args.pattern is not None else pattern_default
        directory = args.directory if args.directory is not None else os.getcwd()
        result = walk(args.action, directory, pattern, excluded, args.dry_run)

        elapsed = round((timer() - start_time) * 1000) / 1000
        logging.info("Elapsed %s seconds" % elapsed)

        sys.exit(result)

    except MessageException as e:
        logging.error(str(e))
        sys.exit(1)
    except SystemExit as e:
        if e.code != 0:
            logging.critical("Terminated with code %s" % e.code)
            sys.exit(e.code)
    except KeyboardInterrupt:
        logging.critical("Terminated by user")
        sys.exit(1)
    except:
        logging.exception(sys.exc_info()[0])
        sys.exit(1)
