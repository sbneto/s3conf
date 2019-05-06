import codecs
import logging
import json
from pathlib import Path

from . import exceptions, config
from .storage import files

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

    def push(self, force=False):
        if not force:
            md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
            hashes = json.load(open(md5_hash_file_name)) if md5_hash_file_name.exists() else {}

        if not force:
            for local_path, remote_path in self.settings.file_mappings.items():
                for local_file, remote_file in self.settings.storages.map(local_path, remote_path):
                    current_hash = hashes.get(str(local_file))
                    if current_hash:
                        with self.settings.storages.remote.open(remote_file) as remote_stream:
                            if current_hash != remote_stream.md5():
                                raise_out_of_sync(local_file, remote_file)
                    else:
                        logger.warning('New mapped file detected: %s', local_file)

        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.settings.storages.upload(local_path, remote_path))
        md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def pull(self):
        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.settings.storages.download(remote_path, local_path))
        md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def get_envfile(self):
        logger.info('Loading configs from {}'.format(self.settings.environment_file_path))
        return files.EnvFile.from_file(self.settings.storages.remote.open(self.settings.environment_file_path))

    def edit(self, create=False):
        with self.settings.storages.remote.open(self.settings.environment_file_path) as remote_stream:
            files.EnvFile.from_file(remote_stream).edit(create=create)
