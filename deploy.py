#!/usr/bin/env python3
try:
    import argparse
    import logging
    from logging import FileHandler, StreamHandler
    import os
    import sys
    from timeit import default_timer as timer
    from getpass import getpass

    from deployment.config import Config
    from deployment.deployment import Deployment
    from deployment.exceptions import MessageException
    from deployment.composer import Composer
    from deployment import encryption

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
        parser.add_argument("--use-encryption", action="store_true", help="use encryption for passwords", default=False)
        parser.add_argument("-d", "--decrypt", action="store_true", help="print decrypted password", default=False)
        parser.add_argument("--decrypt-in-place", action="store_true", help="decrypt password into project config",
                            default=False)
        shared_passphrase_help = "use shared passphrase, this option requires path to persistent file where " \
                                 "shared passphrase verification data is stored"
        parser.add_argument("--shared-passphrase", help=shared_passphrase_help)
        ssh_agent_help = "enable ssh-agent support (ssh-agent, pageant, gpg-agent), requires --shared-passphrase"
        parser.add_argument("--ssh-agent", action="store_true", help=ssh_agent_help)
        ssh_key_help = "what ssh key to use, you can specify either name (ssh-rsa, ssh-ed25519, ...) or by comment"
        parser.add_argument("--ssh-key", help=ssh_key_help)
        args = parser.parse_args()

        deployment = None
        config = None
        try:
            fileName = "deploy"
            if len(args.name) > 0:
                fileName = args.name[0]

            if not os.path.isfile(fileName):
                fileName = ".ftp-%s.json" % fileName

            if not os.path.isfile(fileName):
                logging.error("Configuration file %s doesn't exist" % fileName)
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
                file = FileHandler(os.path.join(config.local, "%s.log" % fileName))
                file.setLevel(logging.INFO)
                file.setFormatter(formatter)
                logger.addHandler(file)

            if args.clear_composer:
                logging.info("Clearing temporary composer directory")
                Composer(config).clear()
                logging.info("Done")
                sys.exit(0)

            if args.use_encryption:
                config.password_encryption = True

            if args.shared_passphrase:
                config.shared_passphrase_verify_file = args.shared_passphrase

            start_time = timer()
            logging.info("Using configuration with name %s" % config.name)

            passphrase = None
            decrypting = args.decrypt or args.decrypt_in_place
            encrypting = config.password_encryption and config.password is not None
            need_passphrase = decrypting or encrypting or config.password_encrypted

            if config.password is None and config.password_encrypted is None:
                config.password = getpass("Password: ")

            if need_passphrase and args.ssh_agent:
                if args.shared_passphrase is None:
                    raise MessageException(
                        "If your want to use --ssh-agent then you need to also use --shared-passphrase"
                    )
                passphrase = encryption.decrypt_passphrase_via_ssh_agent(config, args.ssh_key)

            if decrypting:
                logging.info("Decrypting password...")
                if config.password is not None:
                    raise MessageException("Password is not encrypted")

            if encrypting:
                logging.info("Found plaintext password, please provide your passphrase for encryption:")
                try:
                    encryption.encrypt_config_password(config, passphrase)
                    encryption.save_encrypted_password(config)
                    logging.info("Plaintext password was successfully encrypted")
                except ImportError:
                    raise MessageException(
                        "Encryption is enabled but cryptography dependency is missing, please install requirements.txt"
                    )
            elif config.password_encrypted:
                encryption.decrypt_config_password(config, passphrase)

            if decrypting:
                if args.decrypt_in_place:
                    encryption.save_decrypted_password(config)
                    logging.info("Decrypted password saved into %s" % config.name)
                else:
                    print("Password: %s" % config.password)
                sys.exit(0)

            logging.info("Using %s threads" % config.threads)

            deployment = Deployment(config)
            deployment.dry_run = args.dry_run
            deployment.deploy(args.skip, args.purge_partial, args.purge_only, args.purge_skip, args.force)

            elapsed = round((timer() - start_time) * 1000) / 1000
            logging.info("Elapsed %s seconds" % elapsed)

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
