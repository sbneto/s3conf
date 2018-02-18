import os
import logging
import boto3

from .utils import prepare_path
from .credentials import Credentials


logger = logging.getLogger(__name__)


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


def strip_s3_path(path):
    bucket, _, path = strip_prefix(path, 's3://').partition('/')
    return bucket, path


class S3Storage:
    def __init__(self, credentials=None):
        self._resource = None
        self._credentials = credentials or Credentials()

    def get_resource(self):
        logger.debug('Getting S3 resource')
        # See how boto resolve credentials in
        # http://boto3.readthedocs.io/en/latest/guide/configuration.html#guide-configuration
        if not self._resource:
            logger.debug('Resource does not exist, creating a new one...')
            self._resource = boto3.resource(
                's3',
                aws_access_key_id=self._credentials.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=self._credentials.get('AWS_SECRET_ACCESS_KEY'),
                aws_session_token=self._credentials.get('AWS_SESSION_TOKEN'),
                region_name=self._credentials.get('AWS_S3_REGION_NAME'),
                use_ssl=self._credentials.get('AWS_S3_USE_SSL', True),
                endpoint_url=self._credentials.get('AWS_S3_ENDPOINT_URL'),
            )
        return self._resource

    def __call__(self, file_name):
        return self.read(file_name)

    def _read_file(self, bucket, file_name):
        s3 = self.get_resource()
        file = s3.Object(bucket, file_name).get()
        return file['Body']

    def _write_file(self, f, bucket, path_target):
        s3 = self.get_resource()
        s3.Object(bucket, path_target).upload_fileobj(f)

    def read(self, file_name):
        logger.debug('Reading from %s', file_name)
        bucket, file_name = strip_s3_path(file_name)
        return self._read_file(bucket, file_name)

    def write(self, f, file_name):
        logger.debug('Writing to %s', file_name)
        bucket, path_target = strip_s3_path(file_name)
        self._write_file(f, bucket, path_target)

    def list(self, path):
        logger.debug('Listing %s', path)
        bucket_name, path = strip_s3_path(path)
        bucket = self.get_resource().Bucket(bucket_name)
        for obj in bucket.objects.filter(Prefix=path):
            if not obj.key.endswith('/'):
                yield strip_prefix(obj.key, path)


class LocalStorage:
    def __call__(self, *args, **kwargs):
        self._validate_path(args[0])
        kwargs['mode'] = 'rb'
        return open(*args, **kwargs)

    def _validate_path(self, path):
        if path.startswith('s3://'):
            raise ValueError('LocalStorage can not process S3 paths.')

    def read(self, file_name):
        self._validate_path(file_name)
        return open(file_name, 'rb')

    def write(self, f, file_name):
        self._validate_path(file_name)
        prepare_path(file_name)
        open(file_name, 'wb').write(f.read())

    def list(self, path):
        self._validate_path(path)
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    yield strip_prefix(os.path.join(root, file), path)
        else:
            # the relative path of a file to itself is empty
            yield ''
