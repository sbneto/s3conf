import os
import logging
import boto3
from botocore.exceptions import ClientError
from io import BytesIO

from .utils import prepare_path
from .config import Settings
from . import exceptions


logger = logging.getLogger(__name__)


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


def strip_s3_path(path):
    bucket, _, path = strip_prefix(path, 's3://').partition('/')
    return bucket, path


class BaseStorage:
    def __init__(self, settings=None):
        self._settings = settings or Settings()

    def open(self, file_name, stream=None):
        raise NotImplementedError()

    def write(self, f, file_name):
        raise NotImplementedError()

    def list(self, path):
        raise NotImplementedError()


class S3Storage(BaseStorage):
    def __init__(self, settings=None):
        super(__class__, self).__init__(settings=settings)
        self._resource = None

    def get_resource(self):
        logger.debug('Getting S3 resource')
        # See how boto resolve credentials in
        # http://boto3.readthedocs.io/en/latest/guide/configuration.html#guide-configuration
        if not self._resource:
            logger.debug('Resource does not exist, creating a new one...')
            self._resource = boto3.resource(
                's3',
                aws_access_key_id=self._settings.get('S3CONF_ACCESS_KEY_ID') or self._settings.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=self._settings.get('S3CONF_SECRET_ACCESS_KEY') or self._settings.get('AWS_SECRET_ACCESS_KEY'),
                aws_session_token=self._settings.get('S3CONF_SESSION_TOKEN') or self._settings.get('AWS_SESSION_TOKEN'),
                region_name=self._settings.get('S3CONF_S3_REGION_NAME') or self._settings.get('AWS_S3_REGION_NAME'),
                use_ssl=self._settings.get('S3CONF_S3_USE_SSL') or self._settings.get('AWS_S3_USE_SSL', True),
                endpoint_url=self._settings.get('S3CONF_S3_ENDPOINT_URL') or self._settings.get('AWS_S3_ENDPOINT_URL'),
            )
        return self._resource

    def _read_file_into_stream(self, bucket_name, file_name, stream=None):
        try:
            stream = stream or BytesIO()
            s3 = self.get_resource()
            bucket = s3.Bucket(bucket_name)
            bucket.download_fileobj(file_name, stream)
            stream.seek(0)
            return stream
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.debug('File %s in bucket %s does not exist', file_name, bucket)
                raise exceptions.FileDoesNotExist('s3://{}/{}'.format(bucket_name, file_name))
            else:
                raise

    def _write_file(self, f, bucket_name, path_target):
        s3 = self.get_resource()
        try:
            bucket = s3.create_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyExists':
                bucket = s3.Bucket(bucket_name)
        bucket.upload_fileobj(f, path_target)

    # this is not good, it should return a file like and not mix
    # a "read-into" functionality with the "open" behavior
    # but it works for now, must fix this at some point
    def open(self, file_name, stream=None):
        logger.debug('Reading from %s', file_name)
        bucket, file_name = strip_s3_path(file_name)
        return self._read_file_into_stream(bucket, file_name, stream=stream)

    def write(self, f, file_name):
        logger.debug('Writing to %s', file_name)
        bucket, path_target = strip_s3_path(file_name)
        self._write_file(f, bucket, path_target)

    def list(self, path):
        logger.debug('Listing %s', path)
        bucket_name, path = strip_s3_path(path)
        bucket = self.get_resource().Bucket(bucket_name)
        try:
            for obj in bucket.objects.filter(Prefix=path):
                if not obj.key.endswith('/'):
                    yield strip_prefix(obj.key, path)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.warning('Bucket does not exist, list() returning empty.')
            else:
                raise


class LocalStorage(BaseStorage):
    def _validate_path(self, path):
        if path.startswith('s3://'):
            raise ValueError('LocalStorage can not process S3 paths.')

    def open(self, file_name, stream=None):
        try:
            self._validate_path(file_name)
            stream = stream or BytesIO()
            with open(file_name, 'rb') as f:
                stream.write(f.read())
            stream.seek(0)
            return stream
        except FileNotFoundError:
            raise exceptions.FileDoesNotExist(file_name)

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
            # only yields if it exists
            if os.path.exists(path):
                # the relative path of a file to itself is empty
                # same behavior as in boto3
                yield ''


STORAGES = {
    's3': S3Storage,
    'local': LocalStorage,
}


def get_storage(storage, settings=None):
    if not isinstance(storage, BaseStorage):
        return STORAGES[storage](settings=settings)
    return storage
