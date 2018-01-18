import os
from shutil import rmtree

from s3conf.s3conf import S3Conf
from s3conf.storages import LocalStorage, prepare_path


def test_generate_dict():
    try:
        open('tests/test.env', 'w').write('TEST=123\nTEST2=456\n')

        s3 = S3Conf(storage=LocalStorage())
        data = s3.environment_file('tests/test.env')

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

        s3 = S3Conf(storage=LocalStorage())
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

        s3 = S3Conf(storage=LocalStorage())
        s3.download('tests/remote/', 'tests/local/')

        assert os.path.isfile('tests/local/file1.txt')
        assert os.path.isfile('tests/local/file2.txt')
        assert os.path.isfile('tests/local/subfolder/file3.txt')
        assert os.path.isfile('tests/local/subfolder/file4.txt')
    finally:
        rmtree('tests/local', ignore_errors=True)
        rmtree('tests/remote', ignore_errors=True)
