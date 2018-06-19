import logging
import io
import codecs
from tempfile import NamedTemporaryFile

import editor

from .exceptions import FileDoesNotExist

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

    def read(self):
        return self.storage.open(self.name).read()

    def exists(self):
        if list(self.storage.list(self.name)):
            return True
        return False

    def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.storage.write(io.BytesIO(data), self.name)

    def edit(self, create=False):
        with NamedTemporaryFile(mode='rb+', buffering=0) as f:
            original_data = b''
            try:
                original_data = self.read()
            except FileDoesNotExist:
                if not create:
                    raise
            f.write(original_data)
            edited_data = editor.edit(filename=f.name)

        if edited_data != original_data:
            self.storage.write(io.BytesIO(edited_data), self.name)
        else:
            logger.warning('File not changed. Nothing to write.')


class EnvFile(File):
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
