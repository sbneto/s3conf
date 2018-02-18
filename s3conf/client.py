import logging

import click
from click.exceptions import UsageError

from . import s3conf
from . import storages
from .credentials import Credentials, ConfigFileResolver


logger = logging.getLogger()
logger.setLevel('WARNING')


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option()
@click.option('--debug', is_flag=True)
@click.option('--edit', '-e', is_flag=True)
def main(ctx, debug, edit):
    if debug:
        logger.setLevel('DEBUG')
    if edit:
        if ctx.invoked_subcommand is None:
            try:
                ConfigFileResolver().edit()
            except ValueError as e:
                click.echo(str(e), err=True)
            return
        else:
            raise UsageError('Edit should not be called with a subcommand.', ctx)
    # manually call help in case no relevant settings were defined
    if ctx.invoked_subcommand is None:
        click.echo(main.get_help(ctx))


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
@click.option('--quiet',
              '-q',
              is_flag=True,
              help='Do not print any environment variables output.')
@click.option('--edit',
              '-e',
              is_flag=True)
def env(file, storage, map_files, mapping, dump, dump_path, quiet, edit):
    credentials = Credentials()
    file = file or credentials.get('S3CONF')
    if not file:
        click.echo('No environment file provided. Nothing to be done.', err=True)
        return

    storage = storages.S3Storage(credentials=credentials) if storage == 's3' else storages.LocalStorage()
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
            for var_name, var_value in env_vars.items():
                click.echo('{}={}'.format(var_name, var_value))
        if dump:
            s3conf.phusion_dump(env_vars, dump_path)


if __name__ == '__main__':
    main()
