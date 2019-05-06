import os
import logging
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryFile
from shutil import copyfileobj

import boto3
from botocore.exceptions import ClientError
from google.cloud import storage

from .files import File
from . import exceptions


logger = logging.getLogger(__name__)


# Function : md5sum
# Purpose : Get the md5 hash of a file stored in S3
# Returns : Returns the md5 hash that will match the ETag in S3
# https://stackoverflow.com/questions/6591047/etag-definition-changed-in-amazon-s3/28877788#28877788
# https://github.com/boto/boto3/blob/0cc6042615fd44c6822bd5be5a4019d0901e5dd2/boto3/s3/transfer.py#L169
def md5s3(file_like,
          multipart_threshold=8 * 1024 * 1024,
          multipart_chunksize=8 * 1024 * 1024):
    md5hash = hashlib.md5()
    file_like.seek(0)
    filesize = 0
    block_count = 0
    md5string = b''
    for block in iter(lambda: file_like.read(multipart_chunksize), b''):
        md5hash = hashlib.md5()
        md5hash.update(block)
        md5string += md5hash.digest()
        filesize += len(block)
        block_count += 1

    if filesize > multipart_threshold:
        md5hash = hashlib.md5()
        md5hash.update(md5string)
        md5hash = md5hash.hexdigest() + "-" + str(block_count)
    else:
        md5hash = md5hash.hexdigest()

    file_like.seek(0)
    # https://github.com/aws/aws-sdk-net/issues/815
    return f'"{md5hash}"'


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


class BaseStorage:
    def __init__(self, file_cls=None):
        if file_cls and not issubclass(file_cls, File):
            raise TypeError(f'FileCls must inherit from File')
        self.FileCls = file_cls or File

    def read_into_stream(self, path, stream=None):
        raise NotImplementedError()

    def open(self, path, mode='r', encoding=None):
        logger.debug('Reading from %s', path)
        return self.FileCls(path, storage=self, mode=mode, encoding=encoding)

    def write(self, f, path):
        raise NotImplementedError()

    def list(self, path):
        raise NotImplementedError()


class S3Storage(BaseStorage):
    def __init__(self,
                 aws_access_key_id=None,
                 aws_secret_access_key=None,
                 aws_session_token=None,
                 region_name=None,
                 use_ssl=None,
                 endpoint_url=None,
                 bucket=None,
                 **kwargs):
        super().__init__(**kwargs)
        self.bucket = bucket
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.region_name = region_name
        self.use_ssl = use_ssl
        self.endpoint_url = endpoint_url
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
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_session_token=self.aws_session_token,
                region_name=self.region_name,
                use_ssl=self.use_ssl,
                endpoint_url=self.endpoint_url,
            )
        return self._resource

    def read_into_stream(self, path, stream=None):
        try:
            stream = stream or BytesIO()
            bucket = self.s3.Bucket(self.bucket)
            bucket.download_fileobj(path, stream)
            stream.seek(0)
            return stream
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.debug('File %s in bucket %s does not exist', path, bucket)
                raise exceptions.FileDoesNotExist('s3://{}/{}'.format(self.bucket, path))
            else:
                raise

    def _write(self, f, path):
        bucket = self.s3.Bucket(self.bucket)
        # boto3 closes the handler, creating a copy
        # https://github.com/boto/s3transfer/issues/80
        file_to_close = TemporaryFile()
        f.seek(0)
        copyfileobj(f, file_to_close)
        file_to_close.seek(0)
        bucket.upload_fileobj(file_to_close, path)

    def write(self, f, path):
        logger.debug('Writing to %s', path)
        try:
            self._write(f, path)
        except ClientError:
            self.s3.create_bucket(Bucket=self.bucket)
            self._write(f, path)

    def list(self, path):
        logger.debug('Listing %s', path)
        bucket = self.s3.Bucket(self.bucket)
        path = path.rstrip('/')
        try:
            for obj in bucket.objects.filter(Prefix=path):
                relative_path = strip_prefix(obj.key, path)
                if relative_path.startswith('/') or not relative_path:
                    yield obj.e_tag, relative_path.lstrip('/')
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.warning('Bucket does not exist, list() returning empty.')
            else:
                raise


class GCStorage(BaseStorage):
    def __init__(self, credential_file=None, bucket=None, **kwargs):
        super().__init__(**kwargs)
        self.bucket = bucket
        self.credential_file = credential_file
        self._resource = None

    @property
    def gcs(self):
        logger.debug('Getting GCS resource')
        if not self._resource:
            logger.debug('Resource does not exist, creating a new one...')
            if self.credential_file:
                self._resource = storage.Client.from_service_account_json(self.credential_file)
            else:
                self._resource = storage.Client()
        return self._resource

    def read_into_stream(self, path, stream=None):
        stream = stream or BytesIO()
        bucket = self.gcs.get_bucket(self.bucket)
        blob = bucket.blob(path)
        blob.download_to_file(stream)
        stream.seek(0)
        return stream

    def _write(self, f, path):
        bucket = self.gcs.get_bucket(self.bucket)
        blob = bucket.blob(path)
        f.seek(0)
        blob.upload_from_file(f, path)

    def write(self, f, path):
        logger.debug('Writing to %s', path)
        try:
            self._write(f, path)
        except Exception:
            self.gcs.create_bucket(self.bucket)
            self._write(f, path)

    def list(self, path):
        logger.debug('Listing %s', path)
        bucket = self.gcs.get_bucket(self.bucket)
        path = path.rstrip('/')
        for obj in bucket.list_blobs(prefix=path):
            relative_path = strip_prefix(obj.name, path)
            if relative_path.startswith('/') or not relative_path:
                yield obj.etag, relative_path.lstrip('/')


class LocalStorage(BaseStorage):
    def __init__(self, root='/', **kwargs):
        super().__init__(**kwargs)
        self.root = root

    def build_path(self, path):
        path = path.lstrip('/')
        return os.path.join(self.root, path)

    def read_into_stream(self, path, stream=None):
        try:
            stream = stream or BytesIO()
            with open(path, 'rb') as f:
                stream.write(f.read())
            stream.seek(0)
            return stream
        except FileNotFoundError:
            raise exceptions.FileDoesNotExist(path)

    def write(self, f, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        f.seek(0)
        copyfileobj(f, open(path, 'wb'))

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