import logging
import subprocess
import shlex
import os
from pathlib import Path

import click
import click_log
from click.exceptions import UsageError, MissingParameter

from . import s3conf, config, __version__
from .exceptions import EnvfilePathNotDefinedError, EnvfilePathNotDefinedUsageError
from .storage.exceptions import FileDoesNotExist

logger = logging.getLogger(__name__)


class SectionArgument(click.Argument):
    def handle_parse_result(self, *args, **kwargs):
        try:
            return super().handle_parse_result(*args, **kwargs)
        except MissingParameter:
            raise EnvfilePathNotDefinedUsageError()


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option('--edit', '-e', is_flag=True)
@click.pass_context
# this sets the log level for this app only
@click_log.simple_verbosity_option('s3conf')
def main(ctx, edit):
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
                settings = config.Settings()
                conf = s3conf.S3Conf(settings=settings)
                logger.debug('Using config file %s', settings.config_file)
                storage = conf.storages.storage(settings.config_file)
                with storage.open(settings.config_file, 'r+') as config_file:
                    config_file.edit()
                return
            else:
                raise UsageError('Edit should not be called with a subcommand.')
        # manually call help in case no relevant settings were defined
        if ctx.invoked_subcommand is None:
            click.echo(main.get_help(ctx))
    except FileDoesNotExist as e:
        raise UsageError('The file {} does not exist. Try the "init" command if you want to create it.'.format(str(e)))


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
        conf = s3conf.S3Conf(settings=settings)

        if edit:
            conf.edit(create=create)
        else:
            with conf.get_envfile() as env_file:
                env_vars = env_file.as_dict()
            if map_files:
                conf.pull()
            if not quiet:
                for var_name, var_value in sorted(env_vars.items(), key=lambda x: x[0]):
                    click.echo('{}={}'.format(var_name, var_value))
            if phusion:
                s3conf.phusion_dump(env_vars, phusion_path)
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()
    except FileDoesNotExist as e:
        raise UsageError('The file {} does not exist. Try "-c" option if you want to create it.'.format(str(e)))


@main.command('add')
@click.argument('section', cls=SectionArgument)
@click.argument('local_path')
def add(section, local_path):
    """
    Add a mapping to the S3CONF_MAP variable for the given SECTION pointing to LOCAL_PATH.
    The remote file is mapped to the folder "files" in the same folder of the file pointed by S3CONF.
    """
    try:
        settings = config.Settings(section=section)
        local_path = Path(local_path).resolve().relative_to(settings.root_folder)
        remote_path = os.path.join(os.path.dirname(settings.environment_file_path), 'files', local_path)
        settings.add_mapping(remote_path, local_path)
        config_file = config.ConfigFileResolver(settings.config_file, section=section)
        config_file.set('S3CONF_MAP', settings.serialize_mappings())
        config_file.save()
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


@main.command('rm')
@click.argument('section', cls=SectionArgument)
@click.argument('local_path')
def rm(section, local_path):
    """
    Removes the mapping in the S3CONF_MAP variable for the given SECTION pointing to LOCAL_PATH.
    """
    try:
        settings = config.Settings(section=section)
        local_path = Path(local_path).resolve().relative_to(settings.root_folder)
        settings.rm_mapping(local_path)
        config_file = config.ConfigFileResolver(settings.config_file, section=section)
        config_file.set('S3CONF_MAP', settings.serialize_mappings())
        config_file.save()
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


@main.command('push')
@click.argument('section', cls=SectionArgument)
@click.option('--force',
              '-f',
              is_flag=True)
def push(section, force):
    """
    Upload files mapped in S3CONF_MAP variable defined in s3conf.ini for the given section.
    Stores the md5 hash for uploaded files in local cache. If the remote file md5 hash differs
    from the value we have in our cache, the upload fails unless forced.
    """
    try:
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(settings=settings)
        conf.push(force=force)
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


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
        command = ' '.join(command)

        if not command:
            logger.warning('No command detected.')
            click.echo(exec_command.get_help(ctx))
            return

        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(settings=settings)
        with conf.get_envfile() as env_file:
            env_vars = env_file.as_dict()
        if map_files:
            conf.pull()

        current_env = os.environ.copy()
        current_env.update(env_vars)
        logger.debug('Executing command "%s"', command)
        subprocess.run(shlex.split(command), env=current_env, check=True)
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


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

        with conf.get_envfile(create=create) as env_vars:
            env_vars.set(value)
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


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

        with conf.get_envfile() as env_vars:
            env_vars.unset(value)
    except EnvfilePathNotDefinedError:
        raise EnvfilePathNotDefinedUsageError()


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
    settings = config.Settings(section=section)
    config_file = config.ConfigFileResolver(settings.config_file, section=section)
    config_file.set('S3CONF', remote_file)
    config_file.save()
    conf = s3conf.S3Conf(settings=settings)
    conf.verify_cache()
