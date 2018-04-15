import os
import codecs
import logging
from io import StringIO
from tempfile import NamedTemporaryFile

import editor

from .storages import get_storage, strip_prefix
from .utils import prepare_path
from .config import Settings
from . import exceptions

logger = logging.getLogger(__name__)
__escape_decoder = codecs.getdecoder('unicode_escape')


# inspired by dotenv.main.parse_dotenv(), but operating over a file descriptor
# https://github.com/theskumar/python-dotenv/blob/master/dotenv/main.py
def parse_dotenv(f):
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)

        # Remove any leading and trailing spaces in key, value
        k, v = k.strip(), v.strip().encode('unicode-escape').decode('ascii')

        if len(v) > 0:
            quoted = v[0] == v[len(v) - 1] in ['"', "'"]

            if quoted:
                v = __escape_decoder(v[1:-1])[0]

        yield k, v


def unpack_list(files_list):
    files_pairs = files_list.split(';')
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


def setup_environment(storage='s3',
                      dump=False,
                      dump_path='/etc/container_environment',
                      **kwargs):
    try:
        conf = S3Conf(storage=storage)
        env_vars = conf.environment_file(**kwargs)
        for var_name, var_value in env_vars.items():
            print('{}={}'.format(var_name, var_value))
        if dump:
            phusion_dump(env_vars, dump_path)
    except ValueError as e:
        logger.error(e)
    except Exception as e:
        logger.error(e)
        raise e


class S3Conf:
    def __init__(self, storage='s3', settings=None):
        self.settings = settings or Settings()
        self.storage = get_storage(storage, settings=self.settings)

    @property
    def environment_file_path(self):
        # resolving environment file path
        file_name = self.settings.get('S3CONF')
        if not file_name:
            logger.error('Environemnt file name is not defined or is empty.')
            raise exceptions.EnvfilePathNotDefinedError()

    def map_files(self, files, root_dir=None):
        for file_source, file_target in files:
            self.download(file_source, file_target, root_dir=root_dir)

    def download(self, path, path_target, root_dir=None):
        if root_dir:
            path_target = os.path.join(root_dir, path_target.strip('/'))
        logger.info('Downloading %s to %s', path, path_target)
        for file_path in self.storage.list(path):
            if path.endswith('/') or not path:
                target_name = os.path.join(path_target, file_path)
            else:
                target_name = path_target
            prepare_path(target_name)
            with open(target_name, 'wb') as f:
                # join might add a trailing slash, but we know it is a file, so we remove it
                # stream=f reads the data into f and returns f as our open file
                self.storage.open(os.path.join(path, file_path).rstrip('/'), stream=f)

    def upload(self, path, path_target, root_dir=None):
        if root_dir:
            path = os.path.join(root_dir, path.strip('/'))
        logger.info('Uploading %s to %s', path, path_target)
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_source = os.path.join(root, file)
                    file_target = os.path.join(path_target, strip_prefix(os.path.join(root, file), path).lstrip('/'))
                    self.storage.write(open(file_source, 'rb'), file_target)
        else:
            self.storage.write(open(path, 'rb'), path_target)

    def environment_file(self, map_files=False, mapping='S3CONF_MAP', set_environment=False):
        logger.info('Loading configs from {}'.format(self.environment_file_path))
        try:
            env_vars = dict(parse_dotenv(StringIO(str(self.storage.open(self.environment_file_path).read(), 'utf-8'))))
            if map_files:
                files_list = env_vars.get(mapping)
                if files_list:
                    logger.info('Mapping following files: %s', files_list)
                    files = unpack_list(files_list)
                    self.map_files(files)
            if set_environment:
                for k, v in env_vars.items():
                    os.environ[k] = v
            return env_vars
        except Exception as e:
            logger.error('s3conf was unable to load the environment variables: %s', e)
            raise e

    def edit(self):
        with NamedTemporaryFile(mode='rb+', buffering=0) as f:
            original_data = self.storage.open(self.environment_file_path).read()
            f.write(original_data)
            edited_data = editor.edit(filename=f.name)
            if edited_data != original_data:
                self.upload(f.name, self.environment_file_path)
            else:
                logger.warning('File not changed. Nothing to upload.')
