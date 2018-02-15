import logging
import os

import click

from . import s3conf
from . import storages


logger = logging.getLogger()
logger.setLevel('WARNING')


@click.group()
@click.option('--debug', is_flag=True)
def main(debug):
    if debug:
        logger.setLevel('DEBUG')


@main.command('setup')
@click.option('--path', default=None)
@click.option('--storage', type=click.Choice(['s3', 'local']))
def setup(path, storage):
    storage = None if storage == 's3' else storages.LocalStorage()
    s3conf.setup_environment(path, storage)


if __name__ == '__main__':
    main()
