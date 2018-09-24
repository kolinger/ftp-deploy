import json
import os

from deployment.exceptions import ConfigException


class Config:
    name = None
    threads = 1
    local = None
    secure = False
    host = None
    port = 21
    user = None
    password = None
    remote = None
    retry_count = 10
    ignore = []
    purge = []
    file_log = False
    block_size = 10485760  # 10 MiB

    def __init__(self):
        pass

    def parse(self, file):
        self.name = os.path.splitext(os.path.basename(file))[0]

        with open(file) as file:
            data = json.load(file)

        if self.is_defined('local', data):
            self.local = os.path.realpath(data['local'])

        if self.is_defined('connection', data):
            inner = data['connection']

            if 'threads' in inner:
                self.threads = inner['threads']
                if self.threads < 1:
                    self.threads = 1

            if 'secure' in inner:
                self.secure = inner['secure']

            if self.is_defined('host', inner, 'connection.host'):
                self.host = inner['host']

            if 'port' in inner:
                self.port = inner['port']

            if self.is_defined('user', inner, 'connection.user'):
                self.user = inner['user']

            if self.is_defined('password', inner, 'connection.password'):
                self.password = inner['password']

            if self.is_defined('root', inner, 'connection.root'):
                self.remote = inner['root']

        if 'retry_count' in data:
            self.retry_count = data['retry_count']

        if 'ignore' in data:
            self.ignore = data['ignore']

        if 'purge' in data:
            self.purge = data['purge']

        if 'file_log' in data:
            self.file_log = data['file_log']

        if 'block_size' in data:
            self.block_size = data['block_size']

    def is_defined(self, key, dictionary, description=None):
        if key in dictionary:
            return True
        else:
            if description is None:
                description = key
            raise ConfigException(description + " is not defined")
