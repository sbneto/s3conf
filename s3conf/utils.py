import logging
import hashlib

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
    return '"{}"'.format(md5hash)
