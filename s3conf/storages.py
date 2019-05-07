import os
import codecs
import logging
import difflib
from shutil import copyfileobj
from pathlib import Path
from functools import lru_cache

import editor

from .storage.storages import S3Storage, GCStorage, LocalStorage
from .storage.files import File
from .storage.exceptions import FileDoesNotExist

logger = logging.getLogger(__name__)
__escape_decoder = codecs.getdecoder('unicode_escape')


def parse_env_var(value):
    """
    Split a env var text like

    ENV_VAR_NAME=env_var_value

    into a tuple ('ENV_VAR_NAME', 'env_var_value')
    """
    k, _, v = value.partition('=')

    # Remove any leading and trailing spaces in key, value
    k, v = k.strip(), v.strip().encode('unicode-escape').decode('ascii')

    if v and v[0] == v[-1] in ['"', "'"]:
        v = __escape_decoder(v[1:-1])[0]
    return k, v


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


def partition_path(path):
    protocol, _, path = str(path).partition(':')
    if not path:
        path = protocol
        protocol = 'file'
        bucket = None
    else:
        bucket, _, path = path.lstrip('/').partition('/')
    return protocol, bucket, path


def get_s3_storage(settings, file_class, bucket):
    return S3Storage(
        aws_access_key_id=settings.get('S3CONF_ACCESS_KEY_ID') or settings.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=settings.get('S3CONF_SECRET_ACCESS_KEY') or settings.get('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=settings.get('S3CONF_SESSION_TOKEN') or settings.get('AWS_SESSION_TOKEN'),
        region_name=settings.get('S3CONF_S3_REGION_NAME') or settings.get('AWS_S3_REGION_NAME'),
        use_ssl=settings.get('S3CONF_S3_USE_SSL') or settings.get('AWS_S3_USE_SSL', True),
        endpoint_url=settings.get('S3CONF_S3_ENDPOINT_URL') or settings.get('AWS_S3_ENDPOINT_URL'),
        file_class=file_class,
        bucket=bucket,
    )


def get_gs_storage(settings, file_class, bucket):
    return GCStorage(
        credential_file=settings.get('S3CONF_APPLICATION_CREDENTIALS') or settings.get(
            'GOOGLE_APPLICATION_CREDENTIALS'),
        file_class=file_class,
        bucket=bucket,
    )


def list_all_files(path):
    if path.is_dir():
        mapping = iter(Path(root).joinpath(name).resolve() for root, _, names in os.walk(path) for name in names)
    else:
        mapping = [path]
    return mapping


@lru_cache()
def _make_storage(settings, protocol, bucket):
    try:
        storage = {
            's3': get_s3_storage(settings, BaseFile, bucket),
            'gs': get_gs_storage(settings, BaseFile, bucket),
            'file': LocalStorage(file_class=BaseFile, root=settings.root_folder),
        }[protocol]
    except KeyError:
        storage = LocalStorage(file_class=BaseFile, root=settings.root_folder)
    logger.debug('Using %s storage', storage)
    return storage


class StorageMapper:
    def __init__(self, settings):
        self.settings = settings

    def storage(self, path=''):
        protocol, bucket, _ = partition_path(path)
        logger.debug('Getting storage for %s %s', protocol, bucket)
        return _make_storage(self.settings, protocol, bucket)

    def map(self, source_path, target_path):
        source = self.storage(source_path)
        _, _, source_path = partition_path(source_path)
        _, _, target_path = partition_path(target_path)
        files = {file_path: etag for etag, file_path in source.list(source_path)}
        is_dir = False if len(files) == 1 and source_path in files else True
        if not is_dir:
            yield files[source_path], source_path, target_path
        else:
            for file_path, etag in files.items():
                yield etag, file_path, os.path.join(target_path, os.path.relpath(file_path, source_path))

    def prepare_copy_list(self, source_path, target_path, force=False):
        hashes = []
        to_copy = []
        target = self.storage(target_path)
        _, _, target_path = partition_path(target_path)
        if not force:
            target_hashes = {os.path.join(target_path, file_path): etag for etag, file_path in target.list(target_path)}
        for etag, source_file, target_file in self.map(source_path, target_path):
            if force or target_file not in target_hashes or target_hashes[target_file] != etag:
                to_copy.append((source_file, target_file))
            hashes.append((source_file, target_file, etag))
        return hashes, to_copy

    def copy(self, source_path, target_path, force=False):
        hashes, to_copy = self.prepare_copy_list(source_path, target_path, force)
        source = self.storage(source_path)
        target = self.storage(target_path)
        for source_file, target_file in to_copy:
            with source.open(source_file) as source_stream, target.open(target_file, 'wb') as target_stream:
                copyfileobj(source_stream, target_stream)
        return hashes


class BaseFile(File):
    def exists(self):
        if list(self.storage.list(self.name)):
            return True
        return False

    def md5(self, raise_if_not_exists=True):
        try:
            md5hash, _ = next(self.storage.list(self.name))
        except StopIteration:
            if raise_if_not_exists:
                raise FileDoesNotExist(self.name)
            else:
                md5hash = None
        return md5hash

    def diff(self, file_stream, fromfile='remote', tofile='local', **kwargs):
        file_stream.seek(0)
        self.seek(0)
        result = difflib.unified_diff(
            self.readlines(),
            file_stream.readlines(),
            fromfile=fromfile,
            tofile=tofile,
            **kwargs
        )
        return result

    def edit(self):
        self.seek(0)
        original_data = self.read()
        edited_data = editor.edit(contents=original_data)
        self.seek(0)
        self.truncate()
        self.write(edited_data.decode())


class EnvFile(BaseFile):
    @classmethod
    def from_file(cls, obj):
        obj.__class__ = cls
        return obj

    def as_dict(self):
        env_dict = {}
        try:
            self.seek(0)
            lines = self.read().splitlines()
            lines = [line for line in lines if line and not line.startswith('#') and '=' in line]
            env_dict = dict(parse_env_var(line) for line in lines)
        except FileNotFoundError:
            pass
        return env_dict

    def set(self, value):
        new_key, new_value = parse_env_var(value)
        new_lines = []
        value_set = False
        self.seek(0)
        for line in self.read().splitlines():
            key, value = parse_env_var(line)
            if key == new_key:
                new_lines.append('{}={}'.format(new_key, new_value))
                value_set = True
            else:
                new_lines.append(line)
        if not value_set:
            new_lines.append('{}={}'.format(new_key, new_value))
        self.seek(0)
        self.truncate()
        self.write('\n'.join(new_lines))
        self.file.flush()

    def unset(self, unset_key):
        new_lines = []
        unset_done = False
        try:
            self.seek(0)
            for line in self.read().splitlines():
                key, value = parse_env_var(line)
                if key == unset_key:
                    unset_done = True
                    continue
                else:
                    new_lines.append(line)
        except FileNotFoundError:
            logger.warning('File does not exist')

        if unset_done:
            self.seek(0)
            self.truncate()
            self.write('\n'.join(new_lines))
            self.file.flush()
        else:
            logger.info('Key %s not found in environemnt file, doing nothing...', unset_key)

    def from_dict(self, env_vars):
        file_data = ''
        for var_name, var_value in env_vars.items():
            file_data += '{}={}\n'.format(var_name, var_value)
        self.truncate()
        self.write(file_data)

    def update(self, another_file):
        env_vars = self.as_dict()
        env_vars.update(another_file.as_dict())
        self.from_dict(env_vars)
