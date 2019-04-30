import os
import logging
from io import BytesIO
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from .utils import md5s3
from .files import File
from . import exceptions


logger = logging.getLogger(__name__)


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


def strip_s3_path(path):
    bucket, _, path = strip_prefix(path, 's3://').partition('/')
    return bucket, path


class BaseStorage:
    def __init__(self, settings):
        self._settings = settings

    def read_into_stream(self, file_path, stream=None):
        raise NotImplementedError()

    def open(self, file_name):
        logger.debug('Reading from %s', file_name)
        return File(file_name, storage=self)

    def write(self, f, file_name):
        raise NotImplementedError()

    def list(self, path):
        raise NotImplementedError()


class S3Storage(BaseStorage):
    def __init__(self, settings=None):
        super(__class__, self).__init__(settings=settings)
        self._resource = None

    @property
    def s3(self):
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

    def read_into_stream(self, file_path, stream=None):
        try:
            bucket_name, file_name = strip_s3_path(file_path)
            stream = stream or BytesIO()
            bucket = self.s3.Bucket(bucket_name)
            bucket.download_fileobj(file_name, stream)
            stream.seek(0)
            return stream
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.debug('File %s in bucket %s does not exist', file_name, bucket)
                raise exceptions.FileDoesNotExist('s3://{}/{}'.format(bucket_name, file_name))
            else:
                raise

    def write(self, f, file_name):
        logger.debug('Writing to %s', file_name)
        bucket, path_target = strip_s3_path(file_name)
        try:
            bucket = self.s3.create_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response['Error']['Code'] in (
                'BucketAlreadyExists',
                'BucketAlreadyOwnedByYou',
                'BucketNameUnavailable',
            ):
                bucket = self.s3.Bucket(bucket)
            else:
                raise e
        bucket.upload_fileobj(f, path_target)

    def list(self, path):
        logger.debug('Listing %s', path)
        bucket_name, path = strip_s3_path(path)
        bucket = self.s3.Bucket(bucket_name)
        path = path.rstrip('/')
        try:
            for obj in bucket.objects.filter(Prefix=path):
                relative_path = strip_prefix(obj.key, path)
                if relative_path.startswith('/') or not relative_path:
                    yield obj.e_tag, relative_path
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.warning('Bucket does not exist, list() returning empty.')
            else:
                raise


class LocalStorage(BaseStorage):
    def read_into_stream(self, file_name, stream=None):
        try:
            stream = stream or BytesIO()
            with open(file_name, 'rb') as f:
                stream.write(f.read())
            stream.seek(0)
            return stream
        except FileNotFoundError:
            raise exceptions.FileDoesNotExist(file_name)

    def write(self, f, file_name):
        Path(file_name).parent.mkdir(parents=True, exist_ok=True)
        open(file_name, 'wb').write(f.read())

    def list(self, path):
        path = Path(path)
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                for file in files:
                    yield md5s3(open(file, 'rb')), Path(root).joinpath(file).relative_to(path)
        else:
            # only yields if it exists
            if path.exists():
                # the relative path of a file to itself is empty
                # same behavior as in boto3
                yield md5s3(open(path, 'rb')), ''
