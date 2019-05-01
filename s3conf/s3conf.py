import os
import codecs
import logging
import json
from pathlib import Path

from . import exceptions, files, storages, config

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
        'Upsync failed, target file probably changed since last downsync.\n'
        'Run "sconf downsync" and redo your modifications to avoid conflicts. \n'
        'Run "s3conf diff" to learn more about the modifications.\n'
        'Offending file:\n\n    %s -> %s ',
        local_file,
        remote_file
    )


class S3Conf:
    def __init__(self, storage=None, settings=None):
        self.settings = settings or config.Settings()
        self.storage = storage or storages.S3Storage(settings=self.settings)

    def push(self, force=False):
        if not force:
            md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
            hashes = json.load(open(md5_hash_file_name)) if md5_hash_file_name.exists() else {}

        if not force:
            for local_path, remote_path in self.settings.file_mappings.items():
                mapping = config.expand_mapping(local_path, remote_path)
                for local_file, remote_file in mapping.items():
                    current_hash = hashes.get(str(local_file))
                    if current_hash:
                        with self.storage.open(remote_file) as remote_stream:
                            if current_hash != remote_stream.md5():
                                raise_out_of_sync(local_file, remote_file)
                    else:
                        logger.warning('New mapped file detected: %s', local_file)

        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.upload(local_path, remote_path))
        md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def pull(self):
        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.download(remote_path, local_path))
        md5_hash_file_name = self.settings.cache_dir.joinpath('md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def download(self, remote_path, local_path, force=False):
        hashes = {}
        logger.info('Downloading %s to %s', remote_path, local_path)
        remote_files = {file_path: md5hash for md5hash, file_path in self.storage.list(remote_path)}
        is_dir = False if len(remote_files) == 1 and '' in remote_files else True
        local_storage = storages.LocalStorage(self.settings)
        for file_path, md5hash in remote_files.items():
            target_name = local_path.joinpath(file_path) if is_dir else local_path
            target_name.parent.mkdir(parents=True, exist_ok=True)
            with local_storage.open(target_name) as local_stream:
                existing_md5 = local_stream.md5() if local_stream.exists() and not force else None
                if not existing_md5 or existing_md5 != md5hash:
                    source_name = os.path.join(remote_path, file_path).rstrip('/')
                    logger.debug('Transferring file %s to %s', source_name, target_name)
                    with self.storage.open(source_name) as remote_stream:
                        remote_stream.read_into_stream(local_stream)
            hashes[target_name] = md5hash
        return hashes

    def upload(self, local_path, remote_path):
        logger.info('Uploading %s to %s', local_path, remote_path)
        hashes = {}
        mapping = config.expand_mapping(local_path, remote_path)
        for file_source, file_target in mapping.items():
            with open(file_source, 'rb') as local_stream, self.storage.open(file_target) as remote_stream:
                files.copyfileobj(local_stream, remote_stream)
            hashes[file_source] = remote_stream.md5()
        return hashes

    def get_envfile(self):
        logger.info('Loading configs from {}'.format(self.settings.environment_file_path))
        return files.EnvFile.from_file(self.storage.open(self.settings.environment_file_path))

    def edit(self, create=False):
        with self.storage.open(self.settings.environment_file_path) as remote_stream:
            files.EnvFile.from_file(remote_stream).edit(create=create)
