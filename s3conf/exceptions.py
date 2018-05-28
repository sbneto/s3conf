from click.exceptions import UsageError

from . import config


class EnvfilePathNotDefinedUsageError(UsageError):
    def __init__(self, message=None, *args, **kwargs):
        message = message or ''
        if message:
            message += '\n'
        super().__init__(message, *args, **kwargs)

        error_msg = 'Set the environemnt variable S3CONF or provide a section from an existing config file.'
        try:
            sections_detected = ''
            for section in config.ConfigFileResolver(config.LOCAL_CONFIG_FILE).sections():
                sections_detected += '    {}\n'.format(section)
        except FileNotFoundError:
            pass
        if sections_detected:
            sections_detected = '\n\nThe following sections were detected:\n\n' + sections_detected

        self.message += error_msg + sections_detected


class EnvfilePathNotDefinedError(Exception):
    pass


class FileDoesNotExist(FileNotFoundError):
    pass
