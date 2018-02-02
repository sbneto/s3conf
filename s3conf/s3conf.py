import os
import codecs
import logging
from io import StringIO

from .storages import S3Storage, prepare_path, strip_prefix

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


def setup_environment(file_name=None, storage=None):
    try:
        if not file_name:
            file_name = os.environ.get('S3CONF')
        if not file_name:
            raise ValueError('No environment file provided. Nothing to be done.')
        conf = S3Conf(storage=storage)
        env_vars = conf.environment_file(
            file_name,
            set_environment=True,
            map_files=True,
        )
        for var_name, var_value in env_vars.items():
            print('{}={}'.format(var_name, var_value))
    except ValueError as e:
        logger.error(e)
    except Exception as e:
        logger.error(e)
        raise e


class S3Conf:
    def __init__(self, storage=None):
        self.storage = storage or S3Storage()

    def map_files(self, file_list):
        logger.info('Mapping following files: %s', file_list)
        files = unpack_list(file_list)
        for file_source, file_target in files:
            self.download(file_source, file_target)

    def download(self, path, path_target):
        logger.info('Downloading %s to %s', path, path_target)
        for file_path in self.storage.list(path):
            # join might add a trailing slash, but we know it is a file, so we remove it
            f = self.storage.read(os.path.join(path, file_path).rstrip('/'))
            if path.endswith('/') or not path:
                target_name = os.path.join(path_target, file_path)
            else:
                target_name = path_target
            prepare_path(target_name)
            open(target_name, 'wb').write(f.read())

    def upload(self, path, path_target):
        logger.info('Uploading %s to %s', path, path_target)
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_source = os.path.join(root, file)
                    file_target = os.path.join(path_target, strip_prefix(os.path.join(root, file), path).lstrip('/'))
                    self.storage.write(open(file_source, 'rb'), file_target)
        else:
            self.storage.write(open(path, 'rb'), path_target)

    def environment_file(self, file_name, map_files=False, mapping='S3CONF_MAP',
                         set_environment=False):
        logger.info('Loading configs from {}'.format(str(file_name)))
        if not file_name:
            logger.info('s3conf file_name is not defined or is empty, skipping S3 environment setup.')
            return {}
        try:
            env_vars = dict(parse_dotenv(StringIO(str(self.storage(file_name).read(), 'utf-8'))))
            if map_files:
                files_list = env_vars.get(mapping)
                if files_list:
                    self.map_files(files_list)
            if set_environment:
                for k, v in env_vars.items():
                    os.environ[k] = v
            return env_vars
        except Exception as e:
            logger.error('s3conf was unable to load the environment variables: %s', e)
            raise e
