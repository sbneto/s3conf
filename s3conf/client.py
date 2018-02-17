import logging
import os

import click
import editor

from . import s3conf
from . import storages


logger = logging.getLogger()
logger.setLevel('WARNING')


def edit_config():
    config_file = os.path.expanduser('~/.s3conf/config.ini')
    storages.prepare_path(config_file)
    editor.edit(filename=config_file)


@click.group()
@click.option('--debug', is_flag=True)
@click.option('--edit', '-e', is_flag=True)
def main(debug, edit):
    if debug:
        logger.setLevel('DEBUG')
    if edit:
        edit_config()
        return


def edit_env():
    config_file = os.path.expanduser('~/.s3conf/config.ini')
    # storages.prepare_path(config_file)
    # editor.edit(filename=config_file)


@main.command('env')
@click.option('--file',
              '-f',
              envvar='S3CONF',
              help='Environment file to be used. '
                   'Defaults to the value of S3CONF environment variable if defined.')
@click.option('--storage',
              '-s',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, set the environment during the execution. '
                   'Note that this does not set the environment of the calling process.')
@click.option('--mapping',
              '-a',
              default='S3CONF_MAP',
              show_default=True,
              help='Enviroment variable in the "path" file that contains the file mappings to be '
                   'done if the flag --map-files is defined.')
@click.option('--dump',
              '-d',
              is_flag=True,
              help='If set, dumps variables to --dump-path in for format used by the phusion docker image. '
                   'More information in https://github.com/phusion/baseimage-docker.')
@click.option('--dump-path',
              '-p',
              default='/etc/container_environment',
              show_default=True,
              help='Path where to dump variables as in the phusion docker image format. ')
@click.option('--edit',
              '-e',
              is_flag=True)
def env(file, storage, map_files, mapping, dump, dump_path):
    storage = storages.S3Storage() if storage == 's3' else storages.LocalStorage()
    s3conf.setup_environment(
        file_name=file,
        storage=storage,
        map_files=map_files,
        mapping=mapping,
        dump=dump,
        dump_path=dump_path,
    )


if __name__ == '__main__':
    main()
