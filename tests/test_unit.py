import os
import logging
from shutil import rmtree

import pytest
from click.testing import CliRunner

from s3conf import client, exceptions
from s3conf.s3conf import S3Conf
from s3conf.utils import prepare_path
from s3conf import files

logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('s3transfer').setLevel(logging.ERROR)


def test_cli():
    os.environ['LC_ALL'] = 'C.UTF-8'
    os.environ['LANG'] = 'C.UTF-8'
    runner = CliRunner()
    # result = runner.invoke(client.main, ['env', '--help'])
    # result = runner.invoke(client.main, ['clone'])
    # result = runner.invoke(client.main, ['push'])


def test_prepare_empty_path():
    prepare_path('')


def test_generate_dict():
    try:
        open('tests/test.env', 'w').write('TEST=123\nTEST2=456\n')

        os.environ['S3CONF'] = 'tests/test.env'
        s3 = S3Conf(storage='local')
        data = s3.get_envfile().as_dict()

        assert 'TEST' in data
        assert 'TEST2' in data
        assert data['TEST'] == '123'
        assert data['TEST2'] == '456'
    finally:
        try:
            os.remove('tests/test.env')
        except FileNotFoundError:
            pass


def test_upload_files():
    try:
        prepare_path('tests/local/subfolder/')
        prepare_path('tests/remote/')
        open('tests/local/file1.txt', 'w').write('file1')
        open('tests/local/file2.txt', 'w').write('file2')
        open('tests/local/subfolder/file3.txt', 'w').write('file3')
        open('tests/local/subfolder/file4.txt', 'w').write('file4')

        s3 = S3Conf(storage='local')
        s3.upload('tests/local/', 'tests/remote/')

        assert os.path.isfile('tests/remote/file1.txt')
        assert os.path.isfile('tests/remote/file2.txt')
        assert os.path.isfile('tests/remote/subfolder/file3.txt')
        assert os.path.isfile('tests/remote/subfolder/file4.txt')
    finally:
        rmtree('tests/local', ignore_errors=True)
        rmtree('tests/remote', ignore_errors=True)


def test_download_files():
    try:
        prepare_path('tests/remote/subfolder/')
        prepare_path('tests/local/')
        open('tests/remote/file1.txt', 'w').write('file1')
        open('tests/remote/file2.txt', 'w').write('file2')
        open('tests/remote/subfolder/file3.txt', 'w').write('file3')
        open('tests/remote/subfolder/file4.txt', 'w').write('file4')

        s3 = S3Conf(storage='local')
        s3.download('tests/remote/', 'tests/local/')

        assert os.path.isfile('tests/local/file1.txt')
        assert os.path.isfile('tests/local/file2.txt')
        assert os.path.isfile('tests/local/subfolder/file3.txt')
        assert os.path.isfile('tests/local/subfolder/file4.txt')
    finally:
        rmtree('tests/local', ignore_errors=True)
        rmtree('tests/remote', ignore_errors=True)


def test_no_file_defined():
    with pytest.raises(exceptions.EnvfilePathNotDefinedError):
        del os.environ['S3CONF']
        s3 = S3Conf(storage='local')
        s3.get_envfile().as_dict()


def test_setup_environment():
    try:
        open('tests/test.env', 'w').write(
            'TEST=123\n'
            'TEST2=456\n'
            'S3CONF_MAP=tests/remote/file1.txt:tests/local/file1.txt;'
            'tests/remote/subfolder/:tests/local/subfolder/;'
            '\n'
        )
        prepare_path('tests/remote/subfolder/')
        prepare_path('tests/local/')
        open('tests/remote/file1.txt', 'w').write('file1')
        open('tests/remote/file2.txt', 'w').write('file2')
        open('tests/remote/subfolder/file3.txt', 'w').write('file3')
        open('tests/remote/subfolder/file4.txt', 'w').write('file4')

        s3 = S3Conf(storage='local')
        os.environ['S3CONF'] = 'tests/test.env'
        env_vars = s3.get_envfile().as_dict()
        s3.downsync(env_vars.get('S3CONF_MAP'))

        assert os.path.isfile('tests/local/file1.txt')
        assert os.path.isfile('tests/local/subfolder/file3.txt')
        assert os.path.isfile('tests/local/subfolder/file4.txt')
    finally:
        try:
            os.remove('tests/test.env')
        except FileNotFoundError:
            pass
        rmtree('tests/local', ignore_errors=True)
        rmtree('tests/remote', ignore_errors=True)


def test_file():
    f = files.File('tests/test_file.txt')
    f.write('test')
    assert f.read() == b'test'
    os.remove('tests/test_file.txt')
