import os
from tempfile import NamedTemporaryFile
from configparser import ConfigParser

import editor

from .utils import prepare_path


class EnvironmentResolver:
    def get(self, item, default=None):
        return os.environ.get(item, default)


class ConfigFileResolver:
    DEFAULT_CONFIG_FILE = '~/.s3conf/config.ini'

    def __init__(self, config_file=None, section=None):
        self.config_file = os.path.expanduser(config_file or ConfigFileResolver.DEFAULT_CONFIG_FILE)
        self.section = section or 'default'
        self._config = None

    @property
    def config(self):
        if not self._config:
            self._config = ConfigParser()
            self._config.read(self.config_file)
        return self._config

    @config.setter
    def config(self, value):
        self._config = value

    def get(self, item, default=None):
        return self.config.get(self.section, item, fallback=default)

    def edit(self):
        if os.path.isfile(self.config_file):
            editor.edit(filename=self.config_file)
        else:
            with NamedTemporaryFile(mode='rb+', buffering=0) as f:
                data = editor.edit(filename=f.name)

            if data:
                prepare_path(self.config_file)
                with open(self.config_file, 'wb') as f:
                    f.write(data)
            else:
                raise ValueError('Nothing to write. Config file not created.')


class Credentials:
    def __init__(self, config_file=None, section=None):
        self.resolvers = [
            EnvironmentResolver(),
            ConfigFileResolver(config_file, section)
        ]

    def get(self, item, default=None):
        for resolver in self.resolvers:
            value = resolver.get(item)
            if value:
                break
        else:
            value = default
        return value
