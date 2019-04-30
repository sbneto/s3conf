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


def expand_path(path, path_target):
    mapping = []
    if path.is_dir():
        for root, dirs, files in os.walk(path):
            root_dir = Path(root)
            for file in files:
                file_source = Path(root).joinpath(file)
                file_target = os.path.join(path_target, root_dir.relative_to(path).joinpath(file))
                mapping.append((file_source, file_target))
    else:
        mapping.append((path, path_target))
    return mapping


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
            md5_hash_file_name = os.path.join(self.settings.cache_dir, 'md5')
            hashes = json.load(open(md5_hash_file_name))

        if not force:
            for local_path, remote_path in self.settings.file_mappings.items():
                mapping = expand_path(local_path, remote_path)
                for local_file, remote_file in mapping:
                    current_hash = hashes.get(local_file)
                    if current_hash:
                        if current_hash != self.storage.open(remote_file).md5():
                            raise_out_of_sync(local_file, remote_file)
                    else:
                        logger.warning('New mapped file detected: %s', local_file)

        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.upload(local_path, remote_path))
        md5_hash_file_name = os.path.join(self.settings.cache_dir, 'md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def pull(self):
        hashes = {}
        for local_path, remote_path in self.settings.file_mappings.items():
            hashes.update(self.download(remote_path, local_path))
        md5_hash_file_name = os.path.join(self.settings.cache_dir, 'md5')
        json.dump({str(k): v for k, v in hashes.items()}, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def download(self, path, path_target, force=False):
        hashes = {}
        logger.info('Downloading %s to %s', path, path_target)
        path_target = Path(path_target)
        for md5hash, file_path in self.storage.list(path):
            if path.endswith('/') or not path:
                target_name = path_target.joinpath(file_path)
            else:
                target_name = path_target
            target_name.parent.mkdir(parents=True, exist_ok=True)
            target_file = storages.LocalStorage(self.settings).open(target_name)
            existing_md5 = target_file.md5() if target_file.exists() and not force else None
            if not existing_md5 or existing_md5 != md5hash:
                source_name = os.path.join(path, file_path).rstrip('/')
                logger.debug('Transferring file %s to %s', source_name, target_name)
                with open(target_name, 'wb') as f:
                    # join might add a trailing slash, but we know it is a file, so we remove it
                    self.storage.open(source_name).read_into_stream(f)
            hashes[target_name] = md5hash
        return hashes

    def upload(self, path, path_target):
        logger.info('Uploading %s to %s', path, path_target)
        hashes = {}
        mapping = expand_path(path, path_target)
        for file_source, file_target in mapping:
            file = self.storage.open(file_target)
            file.write(open(file_source, 'rb'))
            hashes[file_source] = file.md5()
        return hashes

    def get_envfile(self):
        logger.info('Loading configs from {}'.format(self.settings.environment_file_path))
        return files.EnvFile.from_file(self.storage.open(self.settings.environment_file_path))

    def edit(self, create=False):
        files.EnvFile.from_file(self.storage.open(self.settings.environment_file_path)).edit(create=create)
