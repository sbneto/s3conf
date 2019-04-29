import os
import logging
import tempfile
from shutil import rmtree

import pytest

from s3conf import exceptions, utils
from s3conf.s3conf import S3Conf
from s3conf import files, config, storages

logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('s3transfer').setLevel(logging.ERROR)


def test_prepare_empty_path():
    utils.prepare_path('')


def test_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        storage = storages.LocalStorage(settings=config.Settings(section='test'))
        test_file = os.path.join(temp_dir, 'test_file.txt')
        f = files.File(test_file, storage)
        f.write('test')
        assert f.read() == b'test'


def test_diff():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        storage = storages.LocalStorage(settings=config.Settings(section='test'))
        f = files.File(os.path.join(temp_dir, 'test.txt'), storage)
        f.write('test1\ntest2\ntest3\n')
        with tempfile.NamedTemporaryFile(mode='w+') as temp_f:
            temp_f.write('test1\ntest2\ntest new\n')
            diff = f.diff(temp_f)
            assert ''.join(diff) == '--- remote\n' \
                                    '+++ local\n' \
                                    '@@ -1,3 +1,3 @@\n' \
                                    ' test1\n' \
                                    ' test2\n' \
                                    '-test3\n' \
                                    '+test new\n'


def _setup_basic_test(temp_dir):
    root_path = os.path.join(temp_dir, 'tests/path1/')
    default_config_file = os.path.join(root_path, f'.{config.CONFIG_NAME}/default.ini')
    utils.prepare_path(default_config_file)
    config_file = os.path.join(root_path, f'{config.CONFIG_NAME}.ini')
    utils.prepare_path(config_file)
    open(default_config_file, 'w').write("""
    [DEFAULT]
        AWS_S3_ENDPOINT_URL=http://localhost:4572
        AWS_ACCESS_KEY_ID=key
        AWS_SECRET_ACCESS_KEY=secret
    """)
    open(config_file, 'w').write("""
    [test]  
        S3CONF=s3://s3conf/test.env
        S3CONF_MAP=s3://s3conf/files/file1.txt:file1.txt;s3://s3conf/files/subfolder/:subfolder/;
        TEST=123
        TEST2=456
    """)

    utils.prepare_path(os.path.join(root_path, 'subfolder/'))
    open(os.path.join(root_path, 'file1.txt'), 'w').write('file1')
    # creating a large file in order to test amazon's modified md5 e_tag
    open(os.path.join(root_path, 'subfolder/file2.txt'), 'w').write('file2' * 1024 * 1024 * 2)
    open(os.path.join(root_path, 'subfolder/file3.txt'), 'w').write('file3')

    os.chdir(root_path)

    return config_file, default_config_file


def test_push_pull_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)

        settings = config.Settings(section='test')
        s3 = S3Conf(settings=settings)

        hashes = s3.push(force=True)

        assert hashes == {
            os.path.join(settings.root_folder, 'file1.txt'): '"826e8142e6baabe8af779f5f490cf5f5"',
            os.path.join(settings.root_folder, 'subfolder/file2.txt'): '"c269c739c5226abab0a4fce7df301155-2"',
            os.path.join(settings.root_folder, 'subfolder/file3.txt'): '"2548729e9c3c60cc3789dfb2408e475d"'
        }

        os.remove(os.path.join(settings.root_folder, 'file1.txt'))
        rmtree(os.path.join(settings.root_folder, 'subfolder'))

        hashes = s3.pull()

        assert hashes == {
            os.path.join(settings.root_folder, 'file1.txt'): '"826e8142e6baabe8af779f5f490cf5f5"',
            os.path.join(settings.root_folder, 'subfolder/file2.txt'): '"c269c739c5226abab0a4fce7df301155-2"',
            os.path.join(settings.root_folder, 'subfolder/file3.txt'): '"2548729e9c3c60cc3789dfb2408e475d"'
        }

        # # must fail unless forced
        # with pytest.raises(exceptions.LocalCopyOutdated):
        #     s3.upsync(local_root, map_files=True)


def test_upload_download_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)

        settings = config.Settings(section='test')
        s3 = S3Conf(settings=settings)

        s3.upload(settings.root_folder, 's3://tests/remote/')
        s3.download('s3://tests/remote/', os.path.join(temp_dir, 'remote/'))

        assert open(os.path.join(temp_dir, 'remote/file1.txt')).read() == 'file1'
        assert open(os.path.join(temp_dir, 'remote/subfolder/file2.txt')).read() == 'file2' * 1024 * 1024 * 2
        assert open(os.path.join(temp_dir, 'remote/subfolder/file3.txt')).read() == 'file3'


def test_no_file_defined():
    with pytest.raises(exceptions.EnvfilePathNotDefinedError), tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        utils.prepare_path(config_file)
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
        config_file, _ = _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        s3 = S3Conf(settings=settings)

        files.File('s3://s3conf/test.env', storage=s3.storage).write('TEST=123\nTEST2=456\n')

        env_vars = s3.get_envfile().as_dict()
        s3.pull()

        assert env_vars['TEST'] == '123'
        assert env_vars['TEST2'] == '456'
        assert open(os.path.join(settings.root_folder, 'file1.txt')).read() == 'file1'
        assert open(os.path.join(settings.root_folder, 'subfolder/file2.txt')).read() == 'file2' * 1024 * 1024 * 2
        assert open(os.path.join(settings.root_folder, 'subfolder/file3.txt')).read() == 'file3'


def test_section_defined_in_settings():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        settings = config.Settings(section='test', config_file=config_file)
        assert settings['TEST'] == '123'
        assert settings['TEST2'] == '456'
        assert settings['TEST3'] == '987'


def test_section_not_defined_in_settings():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)
        os.environ['TEST'] = '321'
        os.environ['TEST2'] = '654'
        os.environ['TEST3'] = '987'
        os.environ['S3CONF'] = 's3://test/in_environment.txt'
        settings = config.Settings(config_file=config_file)
        assert settings['TEST'] == '321'
        assert settings['TEST2'] == '654'
        assert settings['TEST3'] == '987'


def test_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)
        current_path = os.path.join(temp_dir, 'tests/path1/path2/path3/')
        utils.prepare_path(current_path)
        config_folder = config._lookup_root_folder(current_path)
        assert config_folder == os.path.dirname(config_file)


def test_non_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_folder = config._lookup_root_folder(temp_dir)
    assert config_folder == '.'


def test_set_unset_env_var():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, '.s3conf/config')
        utils.prepare_path(config_file)
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

