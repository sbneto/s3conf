import os
import codecs
import logging
from io import StringIO

import boto3

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


def strip_s3_path(file_name):
    bucket, _, file_name = file_name.lstrip('s3://').partition('/')
    return bucket, file_name


def prepare_path(file_target):
    os.makedirs(file_target.rpartition('/')[0], exist_ok=True)


def unpack_list(files_list):
    files_pairs = files_list.split(';')
    files_map = []
    for file_map in files_pairs:
        file_source, _, file_target = file_map.rpartition(':')
        if file_source.startswith('s3://'):
            files_map.append((file_source, file_target))
    return files_map


def setup_environment():
    conf = S3Conf()
    conf.environment_file(os.environ.get('S3CONF'), set_environment=True)


class S3Conf:
    def __init__(self):
        self._resource = None

    def get_resource(self):
        # See how boto resolve credentials in
        # http://boto3.readthedocs.io/en/latest/guide/configuration.html#guide-configuration
        if not self._resource:
            self._resource = boto3.resource(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', None),
                aws_session_token=os.environ.get('AWS_SESSION_TOKEN', None),
                region_name=os.environ.get('AWS_S3_REGION_NAME', None),
                use_ssl=os.environ.get('AWS_S3_USE_SSL', True),
                endpoint_url=os.environ.get('AWS_S3_ENDPOINT_URL', None),
            )
        return self._resource

    def download_file(self, file_name, file_target):
        bucket, file_name = strip_s3_path(file_name)
        prepare_path(file_target)
        s3 = self.get_resource()
        s3.Object(bucket, file_name).download_file(file_target)

    def map_files(self, file_list):
        files = unpack_list(file_list)
        for file_source, file_target in files:
            self.download_file(file_source, file_target)

    def environment_file(self, file_name, map_files=False, mapping='S3CONF_MAP', set_environment=False):
        if not file_name:
            logger.info('s3conf file_name is not defined or is empty, skipping S3 environment setup.')
            return {}
        try:
            bucket, file_name = strip_s3_path(file_name)
            s3 = self.get_resource()
            file = s3.Object(bucket, file_name).get()
            data = StringIO(str(file['Body'].read(), 'utf-8'))
            env_vars = dict(parse_dotenv(data))
            if map_files:
                files_list = env_vars.get(mapping)
                self.map_files(files_list)
            if set_environment:
                for k, v in env_vars.items():
                    os.environ[k] = v
            return env_vars
        except Exception as e:
            logger.error('s3conf was unable to load the environment variables: {}'.format(str(e)))
            raise e

