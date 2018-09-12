import os
import codecs
import logging
import json
from shutil import rmtree

from .utils import prepare_path, md5s3
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


def unpack_list(files_list):
    files_pairs = files_list.split(';') if files_list else []
    files_map = []
    for file_map in files_pairs:
        file_source, _, file_target = file_map.rpartition(':')
        if file_source and file_target:
            files_map.append((file_source, file_target))
    return files_map


def phusion_dump(environment, path):
    prepare_path(path if path.endswith('/') else path + '/')
    for k, v in environment.items():
        with open(os.path.join(path, k), 'w') as f:
            f.write(v + '\n')


def change_root_dir(file_path, root_dir=None):
    if root_dir:
        file_path = os.path.join(root_dir, file_path.lstrip('/'))
    return file_path


def expand_path(path, path_target):
    mapping = []
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                file_source = os.path.join(root, file)
                file_target = os.path.join(path_target,
                                           storages.strip_prefix(os.path.join(root, file), path).lstrip('/'))
                mapping.append((file_source, file_target))
    else:
        mapping.append((path, path_target))
    return mapping


class S3Conf:
    def __init__(self, storage=None, settings=None):
        self.settings = settings or config.Settings()
        self.storage = storage or storages.S3Storage(settings=self.settings)

    @property
    def environment_file_path(self):
        # resolving environment file path
        file_name = self.settings.get('S3CONF')
        if not file_name:
            logger.error('Environemnt file name is not defined or is empty.')
            raise exceptions.EnvfilePathNotDefinedError()
        return file_name

    def upsync(self, local_root, map_files=False, force=False):
        # running operations
        local_environment = change_root_dir(os.path.basename(self.environment_file_path).lstrip('/'), local_root)

        if not force:
            md5_hash_file_name = os.path.join(local_root, '.md5')
            hashes = json.load(open(md5_hash_file_name))

        # checking if md5 hashes have not changed in remote storage since our last downsync
        # if force is set, ignore the hash check and upsync anyway
        if not force and hashes[local_environment] != self.get_envfile().md5():
            raise exceptions.LocalCopyOutdated('Upsync %s -> %s failed', local_environment, self.environment_file_path)
        if map_files:
            local_mapping_root = os.path.join(local_root, 'root')
            env_vars = files.EnvFile(local_environment).as_dict()
            file_map_list = unpack_list(env_vars.get('S3CONF_MAP'))
            if not force:
                for remote_path, local_path in file_map_list:
                    local_path = change_root_dir(local_path, local_mapping_root)
                    mapping = expand_path(local_path, remote_path)
                    for local_file, remote_file in mapping:
                        if hashes[local_file] != self.storage.open(remote_file).md5():
                            raise exceptions.LocalCopyOutdated('Upsync %s -> %s failed', local_file, remote_file)

        self.upload(local_environment, self.environment_file_path)
        if map_files:
            self.upload_mapping(file_map_list, root_dir=local_mapping_root)

    def downsync(self, local_root, map_files=False, wipe=False):
        if wipe:
            rmtree(local_root, ignore_errors=True)
        # running operations
        hashes = {}
        local_path = change_root_dir(os.path.basename(self.environment_file_path).lstrip('/'), local_root)
        hashes.update(self.download(self.environment_file_path, local_path))

        if map_files:
            env_vars = files.EnvFile(local_path).as_dict()
            local_mapping_root = os.path.join(local_root, 'root')
            if env_vars.get('S3CONF_MAP'):
                hashes.update(self.download_mapping(env_vars.get('S3CONF_MAP'), root_dir=local_mapping_root))

        md5_hash_file_name = os.path.join(local_root, '.md5')
        json.dump(hashes, open(md5_hash_file_name, 'w'), indent=4)
        return hashes

    def download_mapping(self, files, root_dir=None):
        if isinstance(files, str):
            files = unpack_list(files)
        hashes = {}
        for remote_file, local_file in files:
            hashes.update(self.download(remote_file, change_root_dir(local_file, root_dir)))
        return hashes

    def upload_mapping(self, files, root_dir=None):
        if isinstance(files, str):
            files = unpack_list(files)
        for remote_file, local_file in files:
            self.upload(change_root_dir(local_file, root_dir), remote_file)

    def download(self, path, path_target, force=False):
        hashes = {}
        logger.info('Downloading %s to %s', path, path_target)
        for md5hash, file_path in self.storage.list(path):
            if path.endswith('/') or not path:
                target_name = os.path.join(path_target, file_path)
            else:
                target_name = path_target
            prepare_path(target_name)
            target_file = files.File(target_name)
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
        mapping = expand_path(path, path_target)
        for file_source, file_target in mapping:
            self.storage.write(open(file_source, 'rb'), file_target)

    def get_envfile(self):
        logger.info('Loading configs from {}'.format(self.environment_file_path))
        return files.EnvFile.from_file(self.storage.open(self.environment_file_path))

    def edit(self, create=False):
        files.EnvFile.from_file(self.storage.open(self.environment_file_path)).edit(create=create)
