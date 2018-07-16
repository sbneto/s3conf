import os
import logging
import tempfile
from shutil import rmtree

import pytest

from s3conf import exceptions
from s3conf.s3conf import S3Conf
from s3conf.utils import prepare_path
from s3conf import files, config, storages

logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('s3transfer').setLevel(logging.ERROR)


def test_prepare_empty_path():
    prepare_path('')


def test_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, 'test_file.txt')
        f = files.File(test_file)
        f.write('test')
        assert f.read() == b'test'


def test_upload_download_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            AWS_S3_ENDPOINT_URL=http://localhost:4572
            AWS_ACCESS_KEY_ID=key
            AWS_SECRET_ACCESS_KEY=secret
            AWS_S3_REGION_NAME=region
            S3CONF=s3://s3conf/test.env
        """)

        prepare_path(os.path.join(temp_dir, 'tests/local/subfolder/'))
        open(os.path.join(temp_dir, 'tests/local/file1.txt'), 'w').write('file1')
        open(os.path.join(temp_dir, 'tests/local/file2.txt'), 'w').write('file2')
        open(os.path.join(temp_dir, 'tests/local/subfolder/file3.txt'), 'w').write('file3')
        open(os.path.join(temp_dir, 'tests/local/subfolder/file4.txt'), 'w').write('file4')

        settings = config.Settings(section='test', config_file=config_file)
        s3 = S3Conf(settings=settings)

        s3.upload(os.path.join(temp_dir, 'tests/local/'), 'tests/remote/')
        s3.download('s3://tests/remote/', os.path.join(temp_dir, 'tests/remote/'))

        assert open(os.path.join(temp_dir, 'tests/remote/file1.txt')).read() == 'file1'
        assert open(os.path.join(temp_dir, 'tests/remote/file2.txt')).read() == 'file2'
        assert open(os.path.join(temp_dir, 'tests/remote/subfolder/file3.txt')).read() == 'file3'
        assert open(os.path.join(temp_dir, 'tests/remote/subfolder/file4.txt')).read() == 'file4'


def test_no_file_defined():
    with pytest.raises(exceptions.EnvfilePathNotDefinedError), tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            AWS_S3_ENDPOINT_URL=http://localhost:4572
            AWS_ACCESS_KEY_ID=key
            AWS_SECRET_ACCESS_KEY=secret
            AWS_S3_REGION_NAME=region
        """)
        os.environ.pop('S3CONF', default=None)
        settings = config.Settings(section='test', config_file=config_file)
        s3 = S3Conf(settings=settings)
        s3.get_envfile().as_dict()


def test_setup_environment():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            AWS_S3_ENDPOINT_URL=http://localhost:4572
            AWS_ACCESS_KEY_ID=key
            AWS_SECRET_ACCESS_KEY=secret
            AWS_S3_REGION_NAME=region
            S3CONF=s3://s3conf/test.env
        """)
        settings = config.Settings(section='test', config_file=config_file)
        storage = storages.S3Storage(settings=settings)
        files.File('s3://tests/remote/file1.txt', storage=storage).write('file1')
        files.File('s3://tests/remote/file2.txt', storage=storage).write('file2')
        files.File('s3://tests/remote/subfolder/file3.txt', storage=storage).write('file3')
        files.File('s3://tests/remote/subfolder/file4.txt', storage=storage).write('file4')

        file_1 = os.path.join(temp_dir, 'file1.txt')
        subfolder = os.path.join(temp_dir, 'subfolder')
        files.File('s3://s3conf/test.env', storage=storage).write("""
        TEST=123
        TEST2=456
        S3CONF_MAP=s3://tests/remote/file1.txt:{};s3://tests/remote/subfolder/:{};
        """.format(file_1, subfolder))

        s3 = S3Conf(settings=settings)
        env_vars = s3.get_envfile().as_dict()
        s3.downsync(env_vars.get('S3CONF_MAP'))

        assert env_vars['TEST'] == '123'
        assert env_vars['TEST2'] == '456'
        assert open(file_1).read() == 'file1'
        assert open(os.path.join(subfolder, 'file3.txt')).read() == 'file3'
        assert open(os.path.join(subfolder, 'file4.txt')).read() == 'file4'


def test_section_defined_in_settings():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            TEST=123
            TEST2=456
        """)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        settings = config.Settings(section='test', config_file=config_file)
        assert settings['TEST'] == '123'
        assert settings['TEST2'] == '456'
        assert settings['TEST3'] == '987'


def test_section_not_defined_in_settings():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            TEST=123
            TEST2=456
        """)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        settings = config.Settings(config_file=config_file)
        assert settings['TEST'] == '321'
        assert settings['TEST2'] == '654'
        assert settings['TEST3'] == '987'


def test_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, 'tests/path1/.s3conf/config')
        prepare_path(config_file)
        current_path = os.path.join(temp_dir, 'tests/path1/path2/path3/')
        prepare_path(current_path)
        open(config_file, 'w').write("""
        [test]
            TEST=123
            TEST2=456
        """)
        config_folder = config._lookup_config_folder(current_path)
        assert config_folder == os.path.dirname(config_file)


def test_non_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_folder = config._lookup_config_folder(temp_dir)
    assert config_folder == os.path.join('.', '.s3conf')


def test_set_unset_env_var():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        prepare_path(config_file)
        open(config_file, 'w').write("""
        [test]
            AWS_S3_ENDPOINT_URL=http://localhost:4572
            AWS_ACCESS_KEY_ID=key
            AWS_SECRET_ACCESS_KEY=secret
            AWS_S3_REGION_NAME=region
            S3CONF=s3://s3conf/test.env
        """)
        settings = config.Settings(section='test', config_file=config_file)
        s3 = S3Conf(settings=settings)

        env_file = s3.get_envfile()
        env_file.set('TEST=123', create=True)

        env_vars = s3.get_envfile().as_dict()
        assert env_vars['TEST'] == '123'

        env_file = s3.get_envfile()
        env_file.unset('TEST')

        env_vars = s3.get_envfile().as_dict()
        assert 'TEST' not in env_vars

