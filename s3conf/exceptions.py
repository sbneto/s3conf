from click.exceptions import UsageError


class EnvfilePathNotDefinedUsageError(UsageError):
    def __init__(self, message=None, *args, **kwargs):
        message = message or ''
        if message:
            message += '\n'
        super().__init__(message, *args, **kwargs)

        error_msg = 'Set the environemnt variable S3CONF or provide a section from an existing config file.'
        try:
            from . import config
            sections_detected = ''
            settings = config.Settings()
            for section in config.ConfigFileResolver(settings.config_file).sections():
                sections_detected += '    {}\n'.format(section)
        except (FileNotFoundError, ImportError):
            pass
        if sections_detected:
            sections_detected = '\n\nThe following sections were detected:\n\n' + sections_detected

        self.message += error_msg + sections_detected


class LocalCopyOutdated(UsageError):
    def __init__(self, message=None, *args, ctx=None):
        message = message or ''
        if message:
            message = message % args
            message += '\n'
        super().__init__(message, ctx=ctx)


class EnvfilePathNotDefinedError(Exception):
    pass

