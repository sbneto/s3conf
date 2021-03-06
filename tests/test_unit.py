import os
import logging
import tempfile
from shutil import rmtree
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

import s3conf.storages
from s3conf import exceptions
from s3conf import config, s3conf

logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('s3transfer').setLevel(logging.ERROR)


def _setup_basic_test(temp_dir):
    root_path = Path(temp_dir).joinpath('tests/path1/')
    default_config_file = root_path.joinpath(f'.{config.CONFIG_NAME}/default.ini')
    default_config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file = root_path.joinpath(f'{config.CONFIG_NAME}.ini')
    config_file.parent.mkdir(parents=True, exist_ok=True)
    open(default_config_file, 'w').write(
        '[DEFAULT]\n'
        'AWS_S3_ENDPOINT_URL=http://localhost:9000\n'
        'AWS_ACCESS_KEY_ID=testtest\n'
        'AWS_SECRET_ACCESS_KEY=testtest\n'
    )
    open(config_file, 'w').write(
        '[test]\n'
        'S3CONF=s3://s3conf/test.env\n'
        'S3CONF_MAP=s3://s3conf/files/file1.txt:file1.txt;s3://s3conf/files/subfolder:subfolder\n'
        'TEST=123\n'
        'TEST2=456\n'
    )

    root_path.joinpath('subfolder/').mkdir(parents=True, exist_ok=True)
    open(root_path.joinpath('file1.txt'), 'w').write('file1')
    # creating a large file in order to test amazon's modified md5 e_tag
    open(root_path.joinpath('subfolder/file2.txt'), 'w').write('file2' * 1024 * 1024 * 2)
    open(root_path.joinpath('subfolder/file3.txt'), 'w').write('file3')

    os.chdir(root_path)

    try:
        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        bucket = conf.storages.storage(settings.environment_file_path).s3.Bucket('s3conf')
        bucket.objects.all().delete()
        bucket.delete()
    except ClientError as e:
        pass

    return config_file, default_config_file


def test_etag():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)

        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        conf.create_envfile()

        local_path = Path(temp_dir).joinpath('tests/path1/file1.txt')
        conf.storages.copy(local_path, 's3://s3conf/remote/file1.txt')
        storage = conf.storages.storage('s3://s3conf/remote/file1.txt')
        file_list = list(storage.list('remote/file1.txt'))
        file = conf.storages.storage(local_path).open(local_path)
        assert file.md5() == file_list[0][0]


def test_copy_list():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        root_folder = Path(settings.root_folder)
        _, mapping = conf.storages.prepare_copy_list(settings.config_file, 's3://s3conf/files/s3conf.ini')
        assert mapping == [
            ('"d219ee6bd8f9e9ddda91cf51f263a883"', str(settings.config_file), 's3://s3conf/files/s3conf.ini'),
        ]
        _, mapping = conf.storages.prepare_copy_list(str(root_folder.joinpath('subfolder')),
                                                   's3://s3conf/files/subfolder')
        assert mapping == [
            (
                '"c269c739c5226abab0a4fce7df301155-2"',
                str(root_folder.joinpath('subfolder/file2.txt')),
                's3://s3conf/files/subfolder/file2.txt',
            ),
            (
                '"2548729e9c3c60cc3789dfb2408e475d"',
                str(root_folder.joinpath('subfolder/file3.txt')),
                's3://s3conf/files/subfolder/file3.txt',
            )
        ]


def test_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        with conf.storages.storage().open('test/test.txt', 'w') as f:
            f.write('test')
        with conf.storages.storage().open('test/test.txt', 'r') as f:
            assert f.read() == 'test'


def test_add_rm():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        settings.add_mapping('s3://s3conf/files/subfolder2', 'subfolder2')
        mapping = settings.serialize_mappings()
        assert mapping == 's3://s3conf/files/file1.txt:file1.txt;' \
                          's3://s3conf/files/subfolder:subfolder;' \
                          's3://s3conf/files/subfolder2:subfolder2'
        settings.rm_mapping('subfolder2')
        mapping = settings.serialize_mappings()
        assert mapping == 's3://s3conf/files/file1.txt:file1.txt;' \
                          's3://s3conf/files/subfolder:subfolder'


def test_diff():
    with tempfile.TemporaryDirectory() as temp_dir:
        _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        storage = conf.storages.storage()
        with storage.open(Path(temp_dir).joinpath('test.txt'), 'w') as f:
            f.write('test1\ntest2\ntest3\n')
        with storage.open(Path(temp_dir).joinpath('test.txt'), 'r') as f, \
                tempfile.NamedTemporaryFile(mode='w+') as temp_f:
            temp_f.write('test1\ntest2\ntest new\n')
            diff = f.diff(temp_f)
            assert ''.join(diff) == '--- remote\n' \
                                    '+++ local\n' \
                                    '@@ -1,3 +1,3 @@\n' \
                                    ' test1\n' \
                                    ' test2\n' \
                                    '-test3\n' \
                                    '+test new\n'


def test_push_pull_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)

        settings = config.Settings(section='test')
        root_folder = Path(settings.root_folder)
        s3 = s3conf.S3Conf(settings=settings)
        s3.create_envfile()

        hashes = s3.push()

        assert hashes == {
            str(root_folder.joinpath('file1.txt')): '"826e8142e6baabe8af779f5f490cf5f5"',
            str(root_folder.joinpath('subfolder/file2.txt')): '"c269c739c5226abab0a4fce7df301155-2"',
            str(root_folder.joinpath('subfolder/file3.txt')): '"2548729e9c3c60cc3789dfb2408e475d"'
        }

        s3.push()

        os.remove(Path(root_folder).joinpath('file1.txt'))
        rmtree(Path(root_folder).joinpath('subfolder'))

        hashes = s3.pull()

        assert hashes == {
            str(root_folder.joinpath('file1.txt')): '"826e8142e6baabe8af779f5f490cf5f5"',
            str(root_folder.joinpath('subfolder/file2.txt')): '"c269c739c5226abab0a4fce7df301155-2"',
            str(root_folder.joinpath('subfolder/file3.txt')): '"2548729e9c3c60cc3789dfb2408e475d"'
        }


def test_copy():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)

        settings = config.Settings(section='test')
        conf = s3conf.S3Conf(settings=settings)
        conf.create_envfile()

        conf.storages.copy(settings.root_folder, 's3://s3conf/remote')
        conf.storages.copy(settings.root_folder, 's3://s3conf/remote')
        conf.storages.copy('s3://s3conf/remote', Path(temp_dir).joinpath('remote'))

        assert open(Path(temp_dir).joinpath('remote/file1.txt')).read() == 'file1'
        assert open(Path(temp_dir).joinpath('remote/subfolder/file2.txt')).read() == 'file2' * 1024 * 1024 * 2
        assert open(Path(temp_dir).joinpath('remote/subfolder/file3.txt')).read() == 'file3'


def test_no_file_defined():
    with pytest.raises(exceptions.EnvfilePathNotDefinedError), tempfile.TemporaryDirectory() as temp_dir:
        config_file = Path(temp_dir).joinpath('.s3conf/config')
        config_file.parent.mkdir(parents=True, exist_ok=True)
        open(config_file, 'w').write("""
        [test]
            AWS_S3_ENDPOINT_URL=http://localhost:4572
            AWS_ACCESS_KEY_ID=key
            AWS_SECRET_ACCESS_KEY=secret
            AWS_S3_REGION_NAME=region
        """)
        os.environ.pop('S3CONF', default=None)
        settings = config.Settings(section='test', config_file=config_file)
        s3 = s3conf.S3Conf(settings=settings)
        with s3.get_envfile() as env_file:
            env_file.as_dict()


def test_setup_environment():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        s3 = s3conf.S3Conf(settings=settings)
        s3.create_envfile()

        with s3.get_envfile('w') as f:
            f.write('TEST=123\nTEST2=456\n')

        with s3.get_envfile() as env_file:
            env_vars = env_file.as_dict()

        s3.pull()

        root_folder = Path(settings.root_folder)
        assert env_vars['TEST'] == '123'
        assert env_vars['TEST2'] == '456'
        assert open(root_folder.joinpath('file1.txt')).read() == 'file1'
        assert open(root_folder.joinpath('subfolder/file2.txt')).read() == 'file2' * 1024 * 1024 * 2
        assert open(root_folder.joinpath('subfolder/file3.txt')).read() == 'file3'


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
        current_path = Path(temp_dir).joinpath('tests/path1/path2/path3/')
        current_path.mkdir(parents=True, exist_ok=True)
        config_folder = Path(config._lookup_root_folder(current_path))
        assert config_folder == config_file.parent.resolve()


def test_non_existing_lookup_config_folder():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_folder = config._lookup_root_folder(temp_dir)
    assert config_folder == Path('.')


def test_set_unset_env_var():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file, _ = _setup_basic_test(temp_dir)
        settings = config.Settings(section='test')
        s3 = s3conf.S3Conf(settings=settings)
        s3.create_envfile()

        with s3.get_envfile(mode='w+') as env_file:
            env_file.set('TEST=123')

            env_vars = env_file.as_dict()
            assert env_vars['TEST'] == '123'

            env_file.unset('TEST')

            env_vars = env_file.as_dict()
            assert 'TEST' not in env_vars
