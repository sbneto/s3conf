import os
import logging
import tempfile
from shutil import rmtree

import pytest

from s3conf import exceptions
from s3conf.s3conf import S3Conf
from s3conf.utils import prepare_path
from s3conf import files, config

logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('s3transfer').setLevel(logging.ERROR)


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
    try:
        f = files.File('tests/test_file.txt')
        f.write('test')
        assert f.read() == b'test'
    finally:
        try:
            os.remove('tests/test_file.txt')
        except FileNotFoundError:
            pass


def test_section_defined_in_settings():
    try:
        open('tests/config', 'w').write("""
        [test]
            TEST=123
            TEST2=456
        """)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        settings = config.Settings(section='test', config_file='tests/config')
        assert settings['TEST'] == '123'
        assert settings['TEST2'] == '456'
        assert settings['TEST3'] == '987'
    finally:
        try:
            os.remove('tests/config')
        except FileNotFoundError:
            pass


def test_section_not_defined_in_settings():
    try:
        open('tests/config', 'w').write("""
        [test]
            TEST=123
            TEST2=456
        """)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        settings = config.Settings(config_file='tests/config')
        assert settings['TEST'] == '321'
        assert settings['TEST2'] == '654'
        assert settings['TEST3'] == '987'
    finally:
        try:
            os.remove('tests/config')
        except FileNotFoundError:
            pass


def test_existing_lookup_config_folder():
    try:
        prepare_path('tests/path1/path2/path3/')
        prepare_path('tests/path1/.s3conf/')
        open('tests/path1/.s3conf/config', 'w').write("""
                [test]
                    TEST=123
                    TEST2=456
                """)
        config_folder = config._lookup_config_folder('tests/path1/path2/path3')
        base_path = os.path.abspath('tests/path1')
        assert config_folder == os.path.join(base_path, '.s3conf')
    finally:
        try:
            rmtree('tests/path1')
        except FileNotFoundError:
            pass


def test_non_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_folder = config._lookup_config_folder(temp_dir)
    assert config_folder == os.path.join('.', '.s3conf')


def test_set_unset_env_var():
    try:
        prepare_path('tests/.s3conf/')
        open('tests/.s3conf/config', 'w').write("""
                [test]
                    AWS_S3_ENDPOINT_URL=http://localhost:4572
                    AWS_ACCESS_KEY_ID=key
                    AWS_SECRET_ACCESS_KEY=secret
                    AWS_S3_REGION_NAME=region
                    S3CONF=s3://s3conf/test.env
                """)
        settings = config.Settings(section='test', config_file='tests/.s3conf/config')
        s3 = S3Conf(settings=settings)

        env_file = s3.get_envfile()
        env_file.set('TEST=123', create=True)

        env_vars = s3.get_envfile().as_dict()
        assert env_vars['TEST'] == '123'

        env_file = s3.get_envfile()
        env_file.unset('TEST')

        env_vars = s3.get_envfile().as_dict()
        assert 'TEST' not in env_vars
    finally:
        try:
            rmtree('tests/.s3conf')
        except FileNotFoundError:
            pass
