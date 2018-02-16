import logging

import click

from . import s3conf
from . import storages


logger = logging.getLogger()
logger.setLevel('WARNING')


@click.group()
@click.option('--debug',
              is_flag=True)
def main(debug):
    if debug:
        logger.setLevel('DEBUG')


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
              help='Storage driver to use. Defaults to the S3 driver. '
                   'Local driver is mainly for testing purpouses.')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, set the environment during the execution. '
                   'Note that this does not set the environment of the calling process.')
@click.option('--mapping',
              '-a',
              default='S3CONF_MAP',
              help='Enviroment variable in the "path" file that contains the file mappings to be '
                   'done if the flag --map-files is defined. Defaults to "S3CONF_MAP".')
@click.option('--dump',
              '-d',
              is_flag=True,
              help='If set, dumps variables to --dump-path in for format used by the phusion docker image. '
                   'More information in https://github.com/phusion/baseimage-docker.')
@click.option('--dump-path',
              '-p',
              default='/etc/container_environment',
              help='Path where to dump variables as in the phusion docker image format. '
                   'Defaults to "/etc/container_environment".')
def setup(file, storage, map_files, mapping, dump, dump_path):
    storage = None if storage == 's3' else storages.LocalStorage()
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
