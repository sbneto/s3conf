import logging
import io
import codecs
import difflib
from tempfile import NamedTemporaryFile

import editor

from . import exceptions
from . import utils

logger = logging.getLogger(__name__)
__escape_decoder = codecs.getdecoder('unicode_escape')


def parse_env_var(value):
    """
    Split a env var text like

    ENV_VAR_NAME=env_var_value

    into a tuple ('ENV_VAR_NAME', 'env_var_value')
    """
    k, _, v = value.partition('=')

    # Remove any leading and trailing spaces in key, value
    k, v = k.strip(), v.strip().encode('unicode-escape').decode('ascii')

    if v and v[0] == v[-1] in ['"', "'"]:
        v = __escape_decoder(v[1:-1])[0]
    return k, v


class File:
    def __init__(self, name, storage=None):
        self.name = name
        self._storage = storage
        self._stream = None

    @property
    def storage(self):
        if not self._storage:
            from .storages import LocalStorage
            self._storage = LocalStorage()
        return self._storage

    def read_into_stream(self, stream):
        self.storage.read_into_stream(self.name, stream=stream)

    def read(self):
        return self.storage.read_into_stream(self.name).read()

    def exists(self):
        if list(self.storage.list(self.name)):
            return True
        return False

    def md5(self, raise_if_not_exists=True):
        try:
            md5hash, _ = next(self.storage.list(self.name))
        except StopIteration:
            if raise_if_not_exists:
                raise exceptions.FileDoesNotExist(self.name)
            else:
                md5hash = None
        return md5hash

    def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.storage.write(io.BytesIO(data), self.name)

    def diff(self, file_stream, fromfile='remote', tofile='local', **kwargs):
        file_stream.seek(0)
        self_str = io.TextIOWrapper(self.storage.read_into_stream(self.name))
        result = difflib.unified_diff(
            self_str.readlines(),
            file_stream.readlines(),
            fromfile=fromfile,
            tofile=tofile,
            **kwargs
        )
        # avoid io.TextIOWrapper closing the stream when being garbage collected
        # https://bugs.python.org/issue21363
        self_str.detach()
        return result

    def edit(self, create=False):
        with NamedTemporaryFile(mode='rb+', buffering=0) as f:
            data_to_edit = b''
            try:
                data_to_edit = self.read()
            except exceptions.FileDoesNotExist:
                if not create:
                    raise

            f.write(data_to_edit)

            original_md5 = self.md5(raise_if_not_exists=False)
            edited_data = editor.edit(filename=f.name)
            new_md5 = utils.md5s3(f)

            if not edited_data and not original_md5:
                logger.warning('Remote file does not exist and no input was provided. '
                               'No attempt to write will be done.')
            elif original_md5 != new_md5:
                # this does not solve concurrency problems, but shrinks the
                # race condition window to a very small period of time
                if original_md5 == self.md5(raise_if_not_exists=False):
                    self.write(edited_data)
                else:
                    f_str = io.TextIOWrapper(f)
                    diff = self.diff(f_str)
                    e = exceptions.LocalCopyOutdated(
                        'Remote file was edited while editing local copy. Diff:\n\n{}'.format(''.join(diff))
                    )
                    # avoid io.TextIOWrapper closing the stream when being garbage collected
                    # https://bugs.python.org/issue21363
                    f_str.detach()
                    raise e
            else:
                logger.warning('File not changed. Nothing to write.')


class EnvFile(File):
    @classmethod
    def from_file(cls, obj):
        obj.__class__ = cls
        return obj

    def as_dict(self):
        env_dict = {}
        try:
            lines = str(self.read(), 'utf-8').splitlines()
            lines = [line for line in lines if line and not line.startswith('#') and '=' in line]
            env_dict = dict(parse_env_var(line) for line in lines)
        except FileNotFoundError:
            pass
        return env_dict

    def set(self, value, create=False):
        new_key, new_value = parse_env_var(value)
        new_lines = []
        value_set = False
        try:
            for line in str(self.read(), 'utf-8').splitlines():
                key, value = parse_env_var(line)
                if key == new_key:
                    new_lines.append('{}={}'.format(new_key, new_value))
                    value_set = True
                else:
                    new_lines.append(line)
        except FileNotFoundError:
            if not create:
                raise
        if not value_set:
            new_lines.append('{}={}'.format(new_key, new_value))
        self.write('\n'.join(new_lines))

    def unset(self, unset_key):
        new_lines = []
        unset_done = False
        try:
            for line in str(self.read(), 'utf-8').splitlines():
                key, value = parse_env_var(line)
                if key == unset_key:
                    unset_done = True
                    continue
                else:
                    new_lines.append(line)
        except FileNotFoundError:
            logger.warning('File does not exist')

        if unset_done:
            self.write('\n'.join(new_lines))
        else:
            logger.info('Key %s not found in environemnt file, doing nothing...', unset_key)

    def from_dict(self, env_vars):
        file_data = ''
        for var_name, var_value in env_vars.items():
            file_data += '{}={}\n'.format(var_name, var_value)
        self.write(file_data)

    def update(self, another_file):
        env_vars = self.as_dict()
        env_vars.update(another_file.as_dict())
        self.from_dict(env_vars)
