import logging

import click
from click.exceptions import UsageError
import click_log

from . import s3conf
from . import storages
from . import config


logger = logging.getLogger(__name__)


def get_settings(section=None):
    if section:
        section = config.Settings(section=section)
    else:
        section = config.Settings()
    return section


@click.group(invoke_without_command=True)
@click.version_option()
@click.option('--edit', '-e', is_flag=True)
@click.option('--global', 'global_settings', is_flag=True)
@click.pass_context
# this sets the log level for this app only
@click_log.simple_verbosity_option('s3conf')
def main(ctx, edit, global_settings):
    """
    Simple command line tool to help manage environment variables stored in a S3-like system. Facilitates editing text
    files remotely stored, as well as downloading and uploading files.
    """
    # configs this module logger to behave properly
    # logger messages will go to stderr (check __init__.py/patch.py)
    # client output should be generated with click.echo() to go to stdout
    click_log.basic_config('s3conf')
    logger.debug('Running main entrypoint')
    if edit:
        if ctx.invoked_subcommand is None:
            try:
                if global_settings:
                    logger.debug('Using config file %s', config.GLOBAL_CONFIG_FILE)
                    config.ConfigFileResolver(config.GLOBAL_CONFIG_FILE).edit()
                else:
                    logger.debug('Using config file %s', config.LOCAL_CONFIG_FILE)
                    config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).edit()
            except ValueError as e:
                logger.error(e)
            return
        else:
            raise UsageError('Edit should not be called with a subcommand.')
    # manually call help in case no relevant settings were defined
    if ctx.invoked_subcommand is None:
        click.echo(main.get_help(ctx))


@main.command('env')
@click.argument('settings', required=False)
@click.option('--storage',
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
              default='S3CONF_MAP',
              show_default=True,
              help='Enviroment variable in the "path" file that contains the file mappings to be '
                   'done if the flag --map-files is defined.')
@click.option('--phusion',
              is_flag=True,
              help='If set, dumps variables to --dump-path in for format used by the phusion docker image. '
                   'More information in https://github.com/phusion/baseimage-docker.')
@click.option('--phusion-path',
              default='/etc/container_environment',
              show_default=True,
              help='Path where to dump variables as in the phusion docker image format.')
@click.option('--quiet',
              '-q',
              is_flag=True,
              help='Do not print any environment variables output.')
@click.option('--edit',
              '-e',
              is_flag=True)
def env(settings, storage, map_files, mapping, phusion, phusion_path, quiet, edit):
    logger.debug('Running env command')
    settings = get_settings(settings)
    try:
        file = settings['S3CONF']
    except KeyError:
        raise UsageError('No environment file provided. Set the environemnt variable S3CONF '
                         'or create a config file. Nothing to be done.')

    storage = storages.S3Storage(settings=settings) if storage == 's3' else storages.LocalStorage()
    conf = s3conf.S3Conf(storage=storage)

    if edit:
        try:
            conf.edit(file)
        except ValueError as e:
            click.echo(str(e), err=True)
    else:
        env_vars = conf.environment_file(
            file,
            map_files=map_files,
            mapping=mapping
        )
        if not quiet:
            for var_name, var_value in sorted(env_vars.items(), key=lambda x: x[0]):
                click.echo('{}={}'.format(var_name, var_value))
        if phusion:
            s3conf.phusion_dump(env_vars, phusion_path)


@main.command('download')
@click.argument('remote_path')
@click.argument('local_path')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
def env(remote_path, local_path, storage):
    """
    Download a file or folder from the S3-like service.

    If REMOTE_PATH has a trailing slash it is considered to be a folder, e.g.: "s3://my-bucket/my-folder/". In this
    case, LOCAL_PATH must be a folder as well. The files and subfolder structure in REMOTE_PATH are copied to
    LOCAL_PATH.

    If REMOTE_PATH does not have a trailing slash, it is considered to be a file, and LOCAL_PATH should be a file as
    well.
    """
    settings = get_settings()
    storage = storages.S3Storage(settings=settings) if storage == 's3' else storages.LocalStorage()
    conf = s3conf.S3Conf(storage=storage)
    conf.download(remote_path, local_path)


@main.command('upload')
@click.argument('local_path')
@click.argument('remote_path')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
def env(remote_path, local_path, storage):
    """
    Upload a file or folder to the S3-like service.

    If LOCAL_PATH is a folder, the files and subfolder structure in LOCAL_PATH are copied to REMOTE_PATH.

    If LOCAL_PATH is a file, the REMOTE_PATH file is created with the same contents.
    """
    settings = get_settings()
    storage = storages.S3Storage(settings=settings) if storage == 's3' else storages.LocalStorage()
    conf = s3conf.S3Conf(storage=storage)
    conf.upload(local_path, remote_path)


if __name__ == '__main__':
    main()
