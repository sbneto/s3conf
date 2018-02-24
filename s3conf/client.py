import logging

import click
from click.exceptions import UsageError

from . import s3conf
from . import storages
from .config import Settings, ConfigFileResolver


logger = logging.getLogger()
logger.setLevel('WARNING')


class MyGroup(click.Group):
    def parse_args(self, ctx, args):
        if args and args[0] in self.commands:
            if len(args) == 1 or args[1] not in self.commands:
                for param in self.params:
                    if param.param_type_name == 'argument':
                        args.insert(0, param.default if param.default is not None else '')
                        break
        super(__class__, self).parse_args(ctx, args)


@click.group(cls=MyGroup, invoke_without_command=True)
@click.version_option()
@click.argument('settings',
                default='default')
@click.option('--config-file',
              default='~/.s3conf/config.ini',
              show_default=True,
              help='Path of the config file to be used.')
@click.option('--debug', is_flag=True)
@click.option('--edit', '-e', is_flag=True)
@click.pass_context
def main(ctx, settings, config_file, debug, edit):
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
    else:
        ctx.obj = {'settings': Settings(config_file=config_file, section=settings)}


@main.command('env')
@click.option('--file',
              '-f',
              envvar='S3CONF',
              help='Environment file to be used. '
                   'Defaults to the value of S3CONF environment variable if defined.')
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
              help='Path where to dump variables as in the phusion docker image format. ')
@click.option('--quiet',
              '-q',
              is_flag=True,
              help='Do not print any environment variables output.')
@click.option('--edit',
              '-e',
              is_flag=True)
@click.pass_context
def env(ctx, file, storage, map_files, mapping, phusion, phusion_path, quiet, edit):
    settings = ctx.obj['settings']
    file = file or settings.get('S3CONF')
    if not file:
        click.echo('No environment file provided. Nothing to be done.', err=True)
        return

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
            for var_name, var_value in env_vars.items():
                click.echo('{}={}'.format(var_name, var_value))
        if phusion:
            s3conf.phusion_dump(env_vars, phusion_path)


if __name__ == '__main__':
    main()
