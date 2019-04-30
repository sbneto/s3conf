import os
import logging
from configobj import ConfigObj
from pathlib import Path

from . import exceptions


logger = logging.getLogger(__name__)


CONFIG_NAME = 's3conf'


def _lookup_root_folder(initial_folder='.'):
    initial_folder = Path(initial_folder)
    # recursion stops
    if not initial_folder or initial_folder == Path(initial_folder.anchor):
        root_folder = Path('.')
        logger.debug('Root folder detected: %s', root_folder)
        return root_folder
    current_path = initial_folder.resolve()
    path_items = {entry.name: entry for entry in os.scandir(current_path)}
    config_file_name = f'{CONFIG_NAME}.ini'
    if config_file_name in path_items:
        entry = path_items[config_file_name]
        if entry.is_file():
            root_folder = Path(entry).parent
            logger.debug('Root folder detected: %s', root_folder)
            return root_folder
    return _lookup_root_folder(current_path.parent)


class EnvironmentResolver:
    def get(self, item, default=None):
        return os.environ.get(item, default)

    def __str__(self):
        return f'environemnt'


class ConfigFileResolver:
    def __init__(self, config_file, section=None):
        self.config_file = config_file
        self.section = section or 'DEFAULT'
        self._config = None

    def __str__(self):
        return f'{self.config_file}:{self.section}'

    @property
    def config(self):
        if not self._config:
            self._config = ConfigObj(str(self.config_file))
        return self._config

    @config.setter
    def config(self, value):
        self._config = value

    def get(self, item, default=None, section=None):
        try:
            return self.config[section or self.section][item]
        except KeyError:
            return default

    def set(self, item, value, section=None):
        self.config.setdefault(section or self.section, {})[item] = value

    def save(self):
        self.config.write()

    def sections(self):
        return list(self.config)


def list_all_files(path):
    if path.is_dir():
        mapping = [Path(root).joinpath(name).resolve() for root, _, names in os.walk(path) for name in names]
    else:
        mapping = [path]
    return mapping


def expand_mapping(local_path, remote_path):
    local_files = list_all_files(local_path)
    if local_path.is_file():
        local_path = local_path.parent
        remote_path = os.path.dirname(remote_path)
    mapping = {f: os.path.join(remote_path, f.relative_to(local_path)) for f in local_files}
    return mapping


class Settings:
    def __init__(self, section=None, config_file=None):
        if config_file:
            self.config_file = Path(config_file).resolve()
            self.root_folder = Path(self.config_file).parent
        else:
            self.root_folder = _lookup_root_folder().resolve()
            self.config_file = self.root_folder.joinpath(f'{CONFIG_NAME}.ini')
        self.cache_dir = self.root_folder.joinpath(f'.{CONFIG_NAME}')
        self.default_config_file = self.cache_dir.joinpath('default.ini')
        self.section = section
        logger.debug('Settings paths:\n%s\n%s\n%s\n%s',
                     self.root_folder,
                     self.config_file,
                     self.cache_dir,
                     self.default_config_file)

        if self.section:
            self.resolvers = [
                ConfigFileResolver(self.config_file, self.section),
                EnvironmentResolver(),
                ConfigFileResolver(self.default_config_file),
            ]
        else:
            self.resolvers = [
                EnvironmentResolver(),
                ConfigFileResolver(self.config_file, self.section),
                ConfigFileResolver(self.default_config_file),
            ]

        self._environment_file_path = None
        self._file_mappings = {}

    @property
    def environment_file_path(self):
        # resolving environment file path
        if not self._environment_file_path:
            self._environment_file_path = self.get('S3CONF')
            if not self._environment_file_path:
                logger.error('Environemnt file name is not defined or is empty.')
                raise exceptions.EnvfilePathNotDefinedError()
        return self._environment_file_path

    @property
    def file_mappings(self):
        if not self._file_mappings:
            files_list = self.get('S3CONF_MAP')
            files_pairs = files_list.split(';') if files_list else []
            for file_map in files_pairs:
                remote_path, _, local_path = file_map.rpartition(':')
                if remote_path and local_path:
                    self.add_mapping(remote_path, local_path)
        return self._file_mappings

    def add_mapping(self, remote_path, local_path):
        local_path = Path(local_path)
        local_path = self.root_folder.joinpath(local_path.relative_to(local_path.root))
        self._file_mappings[local_path] = remote_path

    def serialize_mappings(self):
        file_mappings = {}
        for local_path, remote_path in self.file_mappings.items():
            relative_local_path = local_path.relative_to(self.root_folder)
            file_mappings[relative_local_path] = remote_path
        return ';'.join(f'{remote_path}:{local_path}' for local_path, remote_path in file_mappings.items())

    def create_mapping(self, local_path):
        suffix = local_path.relative_to(self.root_folder)
        return expand_mapping(local_path, os.path.join(os.path.dirname(self.environment_file_path), 'files', suffix))

    def __getitem__(self, item):
        for resolver in self.resolvers:
            value = resolver.get(item)
            if value:
                break
        else:
            raise KeyError()
        logger.debug('Entry %s has value %s found in %s', item, value, str(resolver))
        return value

    def get(self, item, default=None):
        try:
            return self[item]
        except KeyError:
            logger.debug('Key %s not found, returning default %s', item, default)
            return default
