import copy
import json
import logging
import os
import re

from deployment.exceptions import ConfigException


class Config:
    file_path = None
    original_contents = None
    original_data = None
    name = None
    threads = 2
    local = None
    secure = False
    implicit = False
    passive = True
    passive_workaround = False
    connection_limit_wait = 0
    host = None
    port = 21
    user = None
    password = None
    password_encrypted = None
    password_salt = None
    remote = None
    bind = None
    retry_count = 10
    timeout = 10
    ignore = []
    purge = []
    purge_partial = {}
    purge_threads = None
    file_log = False
    block_size = 1048576  # 1 MiB
    composer = None
    password_encryption = False
    shared_passphrase_verify_file = None
    run_before = []
    run_after = []

    def __init__(self):
        pass

    def parse(self, file_path):
        self.file_path = file_path
        self.name = os.path.splitext(os.path.basename(file_path))[0]

        with open(self.file_path, "r") as file:
            contents = file.read()
            self.original_contents = contents
            data = json.loads(contents)
            self.original_data = copy.deepcopy(data)

        if self.is_defined("local", data):
            path = data["local"]
            if re.search(r"^\.($|[/\\])", path):
                directory = os.path.dirname(os.path.realpath(self.file_path))
                if directory:
                    path = directory

            self.local = os.path.realpath(path)

        if self.is_defined("connection", data):
            inner = data["connection"]

            if "threads" in inner:
                self.threads = int(inner["threads"])
                if self.threads < 1:
                    self.threads = 1

            if "secure" in inner:
                self.secure = inner["secure"]

            if "implicit" in inner:
                self.implicit = inner["implicit"]

            if "passive" in inner:
                self.passive = inner["passive"]

            if "passive_workaround" in inner:
                self.passive_workaround = inner["passive_workaround"]

            if "connection_limit_wait" in inner:
                self.connection_limit_wait = int(inner["connection_limit_wait"])

            if self.is_defined("host", inner, "connection.host"):
                self.host = inner["host"]

            if "port" in inner:
                self.port = inner["port"]

            if self.is_defined("user", inner, "connection.user"):
                self.user = inner["user"]

            if self.is_defined("password", inner, "connection.password"):
                self.password = inner["password"]

            if "password_encrypted" in inner:
                self.password_encrypted = inner["password_encrypted"]

            if "password_salt" in inner:
                self.password_salt = inner["password_salt"]

            if "password_encryption" in inner:
                self.password_encryption = inner["password_encryption"]

            if self.is_defined("root", inner, "connection.root"):
                self.remote = inner["root"]
                if self.remote == "/":
                    self.remote = ""

            if "bind" in inner:
                self.bind = inner["bind"]

        if "retry_count" in data:
            self.retry_count = data["retry_count"]

        if "timeout" in data:
            self.timeout = data["timeout"]

        if "ignore" in data:
            self.ignore = data["ignore"]

        if "purge" in data:
            self.purge = data["purge"]

        if "purge_partial" in data:
            self.purge_partial = data["purge_partial"]

        if "purge_threads" in data:
            self.purge_threads = data["purge_threads"]
            if self.purge_threads < 1:
                self.purge_threads = 1

        if "file_log" in data:
            self.file_log = data["file_log"]

        if "block_size" in data:
            self.block_size = data["block_size"]

        if "composer" in data:
            self.composer = data["composer"].lstrip("/")

        if "before" in data:
            self.run_before = data["before"]

        if "after" in data:
            self.run_after = data["after"]

        if self.composer:
            for index, value in enumerate(self.ignore):
                if value.startswith(".ftp-"):
                    logging.warning(
                        "Replacing ignored path " + value + " with /" + value +
                        ", this will break composer otherwise"
                    )
                    self.ignore[index] = "/" + value

    def is_defined(self, key, dictionary, description=None):
        if key in dictionary:
            return True
        else:
            if description is None:
                description = key
            raise ConfigException(description + " is not defined")
