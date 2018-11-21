import logging
import subprocess
import shlex
import os

import click
from click.exceptions import UsageError
import click_log

from . import s3conf, config, exceptions, storages, __version__


logger = logging.getLogger(__name__)


STORAGES = {
    's3': storages.S3Storage,
    'local': storages.LocalStorage,
}


class SectionArgument(click.Argument):
    def handle_parse_result(self, *args, **kwargs):
        try:
            return super().handle_parse_result(*args, **kwargs)
        except click.exceptions.MissingParameter:
            raise exceptions.EnvfilePathNotDefinedUsageError()


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option('--edit', '-e', is_flag=True)
@click.option('--create',
              '-c',
              is_flag=True,
              help='When trying to edit a file, create it if it does not exist.')
@click.pass_context
# this sets the log level for this app only
@click_log.simple_verbosity_option('s3conf')
def main(ctx, edit, create):
    """
    Simple command line tool to help manage environment variables stored in a S3-like system. Facilitates editing text
    files remotely stored, as well as downloading and uploading files.
    """
    # configs this module logger to behave properly
    # logger messages will go to stderr (check __init__.py/patch.py)
    # client output should be generated with click.echo() to go to stdout
    try:
        click_log.basic_config('s3conf')
        logger.debug('Running main entrypoint')
        if edit:
            if ctx.invoked_subcommand is None:
                logger.debug('Using config file %s', config.LOCAL_CONFIG_FILE)
                config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).edit(create=create)
                return
            else:
                raise UsageError('Edit should not be called with a subcommand.')
        # manually call help in case no relevant settings were defined
        if ctx.invoked_subcommand is None:
            click.echo(main.get_help(ctx))
    except exceptions.FileDoesNotExist as e:
        raise UsageError('The file {} does not exist. Try "-c" option if you want to create it.'.format(str(e)))


@main.command('env')
@click.argument('section',
                required=False)
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
@click.option('--create',
              '-c',
              is_flag=True,
              help='When trying to edit a file, create it if it does not exist.')
def env(section, map_files, phusion, phusion_path, quiet, edit, create):
    """
    Reads the file defined by the S3CONF variable and output its contents to stdout. Logs are printed to stderr.
    See options for added functionality: editing file, mapping files, dumping in the phusion-baseimage format, etc.
    """
    try:
        logger.debug('Running env command')
        settings = config.Settings(section=section)
        storage = STORAGES['s3'](settings=settings)
        conf = s3conf.S3Conf(storage=storage, settings=settings)

        if edit:
            conf.edit(create=create)
        else:
            env_vars = conf.get_envfile().as_dict()
            if env_vars.get('S3CONF_MAP') and map_files:
                conf.download_mapping(env_vars.get('S3CONF_MAP'))
            if not quiet:
                for var_name, var_value in sorted(env_vars.items(), key=lambda x: x[0]):
                    click.echo('{}={}'.format(var_name, var_value))
            if phusion:
                s3conf.phusion_dump(env_vars, phusion_path)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()
    except exceptions.FileDoesNotExist as e:
        raise UsageError('The file {} does not exist. Try "-c" option if you want to create it.'.format(str(e)))


@main.command('exec')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file.')
@click.argument('section',
                required=False)
# to use option-like arguments use "--"
# http://click.pocoo.org/6/arguments/#option-like-arguments
@click.argument('command',
                required=False,
                nargs=-1,
                type=click.UNPROCESSED)
@click.pass_context
def exec_command(ctx, section, command, map_files):
    """
    Sets the process environemnt and executes the [COMMAND] in the same context. Does not modify the current shell
    environment.

    If the [COMMAND] has option-like arguments, use the standard POSIX pattern "--" to separate options
    from arguments. Considering our configuration in the "dev" section, we could write:

    s3conf -v info exec dev -- ping -v google.com
    """
    try:
        logger.debug('Running exec command')
        existing_sections = config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).sections()
        command = ' '.join(command)
        if section not in existing_sections:
            command = '{} {}'.format(section, command) if command else section
            section = None

        if not command:
            logger.warning('No command detected.')
            click.echo(exec_command.get_help(ctx))
            return

        settings = config.Settings(section=section)
        storage = STORAGES['s3'](settings=settings)
        conf = s3conf.S3Conf(storage=storage, settings=settings)

        env_vars = conf.get_envfile().as_dict()
        if env_vars.get('S3CONF_MAP') and map_files:
            conf.download_mapping(env_vars.get('S3CONF_MAP'))

        current_env = os.environ.copy()
        current_env.update(env_vars)
        logger.debug('Executing command "%s"', command)
        subprocess.run(shlex.split(command), env=current_env, check=True)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('download')
@click.argument('remote_path')
@click.argument('local_path')
def download(remote_path, local_path):
    """
    Download a file or folder from the S3-like service.

    If REMOTE_PATH has a trailing slash it is considered to be a folder, e.g.: "s3://my-bucket/my-folder/". In this
    case, LOCAL_PATH must be a folder as well. The files and subfolder structure in REMOTE_PATH are copied to
    LOCAL_PATH.

    If REMOTE_PATH does not have a trailing slash, it is considered to be a file, and LOCAL_PATH should be a file as
    well.
    """
    storage = STORAGES['s3']()
    conf = s3conf.S3Conf(storage=storage)
    conf.download(remote_path, local_path)


@main.command('upload')
@click.argument('local_path')
@click.argument('remote_path')
def upload(remote_path, local_path):
    """
    Upload a file or folder to the S3-like service.

    If LOCAL_PATH is a folder, the files and subfolder structure in LOCAL_PATH are copied to REMOTE_PATH.

    If LOCAL_PATH is a file, the REMOTE_PATH file is created with the same contents.
    """
    storage = STORAGES['s3']()
    conf = s3conf.S3Conf(storage=storage)
    conf.upload(local_path, remote_path)


@main.command('downsync')
@click.argument('section', cls=SectionArgument)
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file using the config folder as the '
                   'root directory.')
def downsync(section, map_files):
    """
    For each section defined in the local config file, creates a folder inside the local config folder
    named after the section. Downloads the environemnt file defined by the S3CONF variable for this section
    to this folder.
    """
    try:
        storage = STORAGES['s3']()
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        local_root = os.path.join(config.LOCAL_CONFIG_FOLDER, section)
        conf.downsync(local_root, map_files=map_files)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('upsync')
@click.argument('section', cls=SectionArgument)
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file using the config folder as the '
                   'root directory.')
def upsync(section, map_files):
    """
    For each section defined in the local config file, look up for a folder inside the local config folder
    named after the section. Uploads the environemnt file named as in the S3CONF variable for this section
    to the remote S3CONF path.
    """
    try:
        storage = STORAGES['s3']()
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        local_root = os.path.join(config.LOCAL_CONFIG_FOLDER, section)
        conf.upsync(local_root, map_files=map_files)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('diff')
@click.argument('section', cls=SectionArgument)
def diff(section):
    """
    For each section defined in the local config file, look up for a folder inside the local config folder
    named after the section. Uploads the environemnt file named as in the S3CONF variable for this section
    to the remote S3CONF path.
    """
    try:
        storage = STORAGES['s3']()
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        local_root = os.path.join(config.LOCAL_CONFIG_FOLDER, section)
        click.echo(''.join(conf.diff(local_root)))
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('set')
@click.argument('section', cls=SectionArgument)
@click.argument('value',
                required=False)
@click.option('--create',
              '-c',
              is_flag=True,
              help='When trying to set a variable, create the file if it does not exist.')
def set_variable(section, value, create):
    """
    Set value of a variable in an environment file for the given section.
    If the variable is already defined, its value is replaced, otherwise, it is added to the end of the file.
    The value is given as "ENV_VAR_NAME=env_var_value", e.g.:

    s3conf set test ENV_VAR_NAME=env_var_value
    """
    if not value:
        value = section
        section = None
    try:
        logger.debug('Running env command')
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(settings=settings)

        env_vars = conf.get_envfile()
        env_vars.set(value, create=create)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('unset')
@click.argument('section', cls=SectionArgument)
@click.argument('value',
                required=False)
def unset_variable(section, value):
    """
    Unset a variable in an environment file for the given section.
    The value is given is the variable name, e.g.:

    s3conf unset test ENV_VAR_NAME
    """
    if not value:
        value = section
        section = None
    try:
        logger.debug('Running env command')
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(settings=settings)

        env_vars = conf.get_envfile()
        env_vars.unset(value)
    except exceptions.EnvfilePathNotDefinedError:
        raise exceptions.EnvfilePathNotDefinedUsageError()


@main.command('init')
@click.argument('section')
@click.argument('remote-file')
def init(section, remote_file):
    """
    Creates the .s3conf config folder and .s3conf/config config file
    with the provided section name and configuration file. It is a very
    basic config file. Manually edit it in order to add credentials. E.g.:

    s3conf init development s3://my-project/development.env
    """
    if not remote_file.startswith('s3://'):
        raise UsageError('REMOTE_FILE must be a S3-like path. E.g.:\n\n'
                         's3conf init development s3://my-project/development.env')
    logger.debug('Running init command')
    config_file_path = os.path.join(os.getcwd(), '.s3conf', 'config')
    config_file = config.ConfigFileResolver(config_file_path, section=section)
    config_file.set('S3CONF', remote_file)
    config_file.save()
