import json
import os

from common.singleton import Singleton


class Config:
    __metaclass__ = Singleton

    name = None
    threads = 1
    local = None
    secure = False
    host = None
    port = 21
    user = None
    password = None
    remote = None
    ignore = []
    purge = []

    def __init__(self):
        pass

    def parse(self, file):
        self.name = os.path.splitext(os.path.basename(file))[0]

        with open(file) as file:
            data = json.load(file)

        if self.is_defined('local', data):
            self.local = data['local']

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

        if 'ignore' in data:
            self.ignore = data['ignore']

        if 'purge' in data:
            self.purge = data['purge']

    def is_defined(self, key, dictionary, description=None):
        if key in dictionary:
            return True
        else:
            if description is None:
                description = key
            raise ConfigException(description + " is not defined")


class ConfigException(Exception):
    pass
