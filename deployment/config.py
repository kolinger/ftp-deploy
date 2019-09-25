import json
import logging
import os

from deployment.exceptions import ConfigException


class Config:
    name = None
    threads = 2
    local = None
    secure = False
    passive = True
    host = None
    port = 21
    user = None
    password = None
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
    run_before = []
    run_after = []

    def __init__(self):
        pass

    def parse(self, file):
        self.name = os.path.splitext(os.path.basename(file))[0]

        with open(file) as file:
            data = json.load(file)

        if self.is_defined("local", data):
            self.local = os.path.realpath(data["local"])

        if self.is_defined("connection", data):
            inner = data["connection"]

            if "threads" in inner:
                self.threads = inner["threads"]
                if self.threads < 1:
                    self.threads = 1

            if "secure" in inner:
                self.secure = inner["secure"]

            if "passive" in inner:
                self.passive = inner["passive"]

            if self.is_defined("host", inner, "connection.host"):
                self.host = inner["host"]

            if "port" in inner:
                self.port = inner["port"]

            if self.is_defined("user", inner, "connection.user"):
                self.user = inner["user"]

            if self.is_defined("password", inner, "connection.password"):
                self.password = inner["password"]

            if self.is_defined("root", inner, "connection.root"):
                self.remote = inner["root"]

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
