import logging
import subprocess
import shlex
import os
from shutil import rmtree

import click
from click.exceptions import UsageError
import click_log

from . import s3conf, config, files, exceptions


logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.version_option()
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
@click.option('--create',
              '-c',
              is_flag=True,
              help='When trying to edit a file, create it if it does not exist.')
def env(section, storage, map_files, phusion, phusion_path, quiet, edit, create):
    """
    Reads the file defined by the S3CONF variable and output its contents to stdout. Logs are printed to stderr.
    See options for added functionality: editing file, mapping files, dumping in the phusion-baseimage format, etc.
    """
    try:
        logger.debug('Running env command')
        settings = config.Settings(section=section)
        conf = s3conf.S3Conf(storage=storage, settings=settings)

        if edit:
            conf.edit(create=create)
        else:
            env_vars = conf.get_envfile().as_dict()
            if env_vars.get('S3CONF_MAP') and map_files:
                conf.downsync(env_vars.get('S3CONF_MAP'))
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
    except exceptions.FileDoesNotExist as e:
        raise UsageError('The file {} does not exist. Try "-c" option if you want to create it.'.format(str(e)))


@main.command('exec')
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
@click.argument('section',
                required=False)
# to use option-like arguments use "--"
# http://click.pocoo.org/6/arguments/#option-like-arguments
@click.argument('command',
                required=False,
                nargs=-1,
                type=click.UNPROCESSED)
@click.pass_context
def exec_command(ctx, section, command, storage, map_files):
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
        conf = s3conf.S3Conf(storage=storage, settings=settings)

        env_vars = conf.get_envfile().as_dict()
        if env_vars.get('S3CONF_MAP') and map_files:
            conf.downsync(env_vars.get('S3CONF_MAP'))

        current_env = os.environ.copy()
        current_env.update(env_vars)
        logger.debug('Executing command "%s"', command)
        subprocess.run(shlex.split(command), env=current_env, check=True)
    except exceptions.EnvfilePathNotDefinedError:
        error_msg = 'Set the environemnt variable S3CONF or provide a section from an existing config file.'
        try:
            sections_detected = ''
            for section in existing_sections:
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


@main.command('downsync')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file using the config folder as the '
                   'root directory.')
def downsync(storage, map_files):
    """
    For each section defined in the local config file, creates a folder inside the local config folder
    named after the section. Downloads the environemnt file defined by the S3CONF variable for this section
    to this folder.
    """
    local_resolver = config.ConfigFileResolver(config.LOCAL_CONFIG_FILE)

    for section in local_resolver.sections():
        settings = config.Settings(section=section)

        # preparing paths
        s3conf_env_file = settings['S3CONF']
        local_root = os.path.join(config.LOCAL_CONFIG_FOLDER, section)
        rmtree(local_root, ignore_errors=True)

        # running operations
        local_path = os.path.join(local_root, os.path.basename(s3conf_env_file).lstrip('/'))
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        remote_env_file = conf.get_envfile()
        local_env_file = files.EnvFile(local_path)
        local_env_file.write(remote_env_file.read())

        if map_files:
            env_vars = local_env_file.as_dict()
            local_mapping_root = os.path.join(local_root, 'root')
            if env_vars.get('S3CONF_MAP'):
                conf.downsync(env_vars.get('S3CONF_MAP'), root_dir=local_mapping_root)


@main.command('upsync')
@click.option('--storage',
              type=click.Choice(['s3', 'local']),
              default='s3',
              show_default=True,
              help='Storage driver to use. Local driver is mainly for testing purpouses.')
@click.option('--map-files',
              '-m',
              is_flag=True,
              help='If defined, tries to map files from the storage to the local drive as defined by '
                   'the variable S3CONF_MAP read from the S3CONF file using the config folder as the '
                   'root directory.')
def upsync(storage, map_files):
    """
    For each section defined in the local config file, look up for a folder inside the local config folder
    named after the section. Uploads the environemnt file named as in the S3CONF variable for this section
    to the remote S3CONF path.
    """
    local_resolver = config.ConfigFileResolver(config.LOCAL_CONFIG_FILE)

    for section in local_resolver.sections():
        settings = config.Settings(section=section)

        # preparing paths
        s3conf_env_file = settings['S3CONF']
        local_root = os.path.join(config.LOCAL_CONFIG_FOLDER, section)

        # running operations
        local_path = os.path.join(local_root, os.path.basename(s3conf_env_file).lstrip('/'))
        conf = s3conf.S3Conf(storage=storage, settings=settings)
        remote_env_file = conf.get_envfile()
        local_env_file = files.EnvFile(local_path)
        remote_env_file.write(local_env_file.read())

        if map_files:
            env_vars = local_env_file.as_dict()
            local_mapping_root = os.path.join(local_root, 'root')
            if env_vars.get('S3CONF_MAP'):
                conf.upsync(env_vars.get('S3CONF_MAP'), root_dir=local_mapping_root)


if __name__ == '__main__':
    main()
