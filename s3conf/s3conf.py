import codecs
import logging
import json
from pathlib import Path

from . import exceptions, config
from .storages import StorageMapper, EnvFile, partition_path

logger = logging.getLogger(__name__)
__escape_decoder = codecs.getdecoder('unicode_escape')


def parse_dotenv(data):
    for line in data.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')

            # Remove any leading and trailing spaces in key, value
            k, v = k.strip(), v.strip().encode('unicode-escape').decode('ascii')

            if v and v[0] == v[-1] in ['"', "'"]:
                v = __escape_decoder(v[1:-1])[0]

            yield k, v


def phusion_dump(environment, path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    for k, v in environment.items():
        with open(path.joinpath(k), 'w') as f:
            f.write(v + '\n')


def raise_out_of_sync(local_file, remote_file):
    raise exceptions.LocalCopyOutdated(
        'Upload failed, remote file probably changed since last download and md5 hashes in cache conflict.\n'
        'If you want to upload anyway, use the -f flag. \n'
        'Offending file:\n\n    %s -> %s ',
        local_file,
        remote_file
    )


class S3Conf:
    def __init__(self, settings=None):
        self.settings = settings or config.Settings()
        self._storages = None

    @property
    def storages(self):
        if not self._storages:
            self._storages = StorageMapper(self.settings)
        return self._storages

    def verify_cache(self):
        cache_dir = Path(self.settings.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        default_config_file = config.ConfigFileResolver(self.settings.default_config_file, section='DEFAULT')
        default_config_file.save()
        gitignore_file_path = cache_dir.joinpath('.gitignore')
        open(gitignore_file_path, 'w').write('*\n')

    def check_remote_changes(self):
        local_hashes = json.load(open(self.settings.hash_file)) if Path(self.settings.hash_file).exists() else {}
        for local_path, remote_path in self.settings.file_mappings.items():
            remote_hashes = self.storages.list(remote_path)
            for _, local_file, remote_file in self.storages.expand_path(local_path, remote_path):
                local_hash = local_hashes.get(str(local_file))
                remote_hash = remote_hashes.get(str(remote_file))
                if local_hash:
                    if local_hash != remote_hash:
                        raise_out_of_sync(local_file, remote_file)
                else:
                    logger.warning('New mapped file detected: %s', local_file)

    def push(self, force=False):
        if not force:
            self.check_remote_changes()
        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            copy_hashes = self.storages.copy(local_path, remote_path)
            hashes.update({str(local_file): local_hash for local_hash, local_file, _ in copy_hashes})
        self.verify_cache()
        json.dump(hashes, open(self.settings.hash_file, 'w'), indent=4)
        return hashes

    def pull(self):
        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            copy_hashes = self.storages.copy(remote_path, local_path)
            hashes.update({str(local_file): remote_hash for remote_hash, _, local_file in copy_hashes})
        self.verify_cache()
        json.dump(hashes, open(self.settings.hash_file, 'w'), indent=4)
        return hashes

    def get_envfile(self, mode='r'):
        logger.info('Loading configs from %s', self.settings.environment_file_path)
        remote_storage = self.storages.storage(self.settings.environment_file_path)
        _, _, path = partition_path(self.settings.environment_file_path)
        return EnvFile.from_file(remote_storage.open(path, mode=mode))

    def edit_envfile(self):
        with self.get_envfile(mode='r+') as envfile:
            envfile.edit()

    def create_envfile(self):
        logger.info('Trying to create envifile %s', self.settings.environment_file_path)
        remote_storage = self.storages.storage(self.settings.environment_file_path)
        _, _, path = partition_path(self.settings.environment_file_path)
        envfile_exist = bool(list(remote_storage.list(path)))
        if envfile_exist:
            logger.warning('%s already exist', self.settings.environment_file_path)
        else:
            with self.get_envfile(mode='w') as _:
                pass
