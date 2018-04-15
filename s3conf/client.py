import logging
from os import path
from shutil import rmtree

import click
from click.exceptions import UsageError
import click_log

from . import s3conf
from . import config
from . import exceptions


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
            if global_settings:
                logger.debug('Using config file %s', config.GLOBAL_CONFIG_FILE)
                config.ConfigFileResolver(config.GLOBAL_CONFIG_FILE).edit()
            else:
                logger.debug('Using config file %s', config.LOCAL_CONFIG_FILE)
                config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).edit()
            return
        else:
            raise UsageError('Edit should not be called with a subcommand.')
    # manually call help in case no relevant settings were defined
    if ctx.invoked_subcommand is None:
        click.echo(main.get_help(ctx))


@main.command('env')
@click.argument('section',
                required=False)
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file.')
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
def env(section, storage, map_files, phusion, phusion_path, quiet, edit):
    """
    Reads the file defined by the S3CONF variable and output its contents to stdout. Logs are printed to stderr.
    See options for added functionality: editing file, mapping files, dumping in the phusion-baseimage format, etc.
    """
    try:
        logger.debug('Running env command')
        settings = get_settings(section)
        conf = s3conf.S3Conf(storage=storage, settings=settings)

        if edit:
            conf.edit()
        else:
            env_vars = conf.get_variables()
            if env_vars.get('S3CONF_MAP') and map_files:
                conf.map_files(env_vars.get('S3CONF_MAP'))
            if not quiet:
                for var_name, var_value in sorted(env_vars.items(), key=lambda x: x[0]):
                    click.echo('{}={}'.format(var_name, var_value))
            if phusion:
                s3conf.phusion_dump(env_vars, phusion_path)
    except exceptions.EnvfilePathNotDefinedError:
        error_msg = 'Set the environemnt variable S3CONF or provide a section from an existing config file.'
        try:
            sections_detected = ''
            for section in config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).sections():
                sections_detected += '    {}\n'.format(section)
        except FileNotFoundError:
            pass
        if sections_detected:
            sections_detected = '\n\nThe following sections were detected:\n\n' + sections_detected
        raise UsageError(error_msg + sections_detected)


@main.command('download')
@click.argument('remote_path')
@click.argument('local_path')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
def download(remote_path, local_path, storage):
    """
    Download a file or folder from the S3-like service.

    If REMOTE_PATH has a trailing slash it is considered to be a folder, e.g.: "s3://my-bucket/my-folder/". In this
    case, LOCAL_PATH must be a folder as well. The files and subfolder structure in REMOTE_PATH are copied to
    LOCAL_PATH.

    If REMOTE_PATH does not have a trailing slash, it is considered to be a file, and LOCAL_PATH should be a file as
    well.
    """
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
def upload(remote_path, local_path, storage):
    """
    Upload a file or folder to the S3-like service.

    If LOCAL_PATH is a folder, the files and subfolder structure in LOCAL_PATH are copied to REMOTE_PATH.

    If LOCAL_PATH is a file, the REMOTE_PATH file is created with the same contents.
    """
    conf = s3conf.S3Conf(storage=storage)
    conf.upload(local_path, remote_path)


@main.command('clone')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
def clone(storage):
    """
    For each section defined in the local config file, creates a folder inside the local config folder
    named after the section. Downloads the environemnt file defined by the S3CONF variable for this section
    to this folder.
    """
    local_resolver = config.ConfigFileResolver(config.LOCAL_CONFIG_FILE)

    for section in local_resolver.sections():
        settings = get_settings(section=section)
        # removing environment resolver, we only want config file onwards on our chain
        settings.resolvers = settings.resolvers[1:]

        # preparing paths
        s3conf_env_file = settings['S3CONF']
        local_root = path.join(config.LOCAL_CONFIG_FOLDER, section)
        rmtree(local_root, ignore_errors=True)

        # running operations
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        conf.download(s3conf_env_file, path.basename(s3conf_env_file), root_dir=local_root)


@main.command('push')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
def push(storage):
    """
    For each section defined in the local config file, look up for a folder inside the local config folder
    named after the section. Uploads the environemnt file named as in the S3CONF variable for this section
    to the remote S3CONF path.
    """
    local_resolver = config.ConfigFileResolver(config.LOCAL_CONFIG_FILE)

    for section in local_resolver.sections():
        settings = get_settings(section=section)
        # removing environment resolver, we only want config file onwards on our chain
        settings.resolvers = settings.resolvers[1:]

        # preparing paths
        s3conf_env_file = settings['S3CONF']
        local_root = path.join(config.LOCAL_CONFIG_FOLDER, section)

        # running operations
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        conf.upload(path.basename(s3conf_env_file), s3conf_env_file, root_dir=local_root)


if __name__ == '__main__':
    main()
