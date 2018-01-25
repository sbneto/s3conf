import os
import boto3


def strip_s3_path(path):
    bucket, _, path = path.lstrip('s3://').partition('/')
    return bucket, path


def prepare_path(file_target):
    os.makedirs(file_target.rpartition('/')[0], exist_ok=True)


def strip_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text


class S3Storage:
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
        bucket, file_name = strip_s3_path(file_name)
        return self._read_file(bucket, file_name)

    def write(self, f, file_name):
        bucket, path_target = strip_s3_path(file_name)
        self._write_file(f, bucket, path_target)

    def list(self, path):
        bucket_name, path = strip_s3_path(path)
        bucket = self.get_resource().Bucket(bucket_name)
        for obj in bucket.objects.filter(Prefix=path):
            if not obj.key.endswith('/'):
                yield strip_prefix(obj.key, path), self._read_file(bucket_name, obj.key)


class LocalStorage:
    def __call__(self, *args, **kwargs):
        kwargs['mode'] = 'rb'
        return open(*args, **kwargs)

    def read(self, file_name):
        return open(file_name, 'rb')

    def write(self, f, file_name):
        prepare_path(file_name)
        open(file_name, 'wb').write(f.read())

    def list(self, path):
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_name = os.path.join(root, file)
                    yield strip_prefix(file_name, path), open(file_name, 'rb')
        else:
            yield path, open(path, 'rb')
