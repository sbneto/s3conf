import logging
import io
import codecs
from tempfile import NamedTemporaryFile

import editor

from .storages import LocalStorage

logger = logging.getLogger(__name__)
__escape_decoder = codecs.getdecoder('unicode_escape')


class File:
    def __init__(self, name, storage=None):
        self.name = name
        self.storage = storage or LocalStorage()
        self._stream = None

    def read(self):
        return self.storage.open(self.name).read()

    def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.storage.write(io.BytesIO(data), self.name)

    def edit(self):
        with NamedTemporaryFile(mode='rb+', buffering=0) as f:
            original_data = self.read()
            f.write(original_data)
            edited_data = editor.edit(filename=f.name)
            if edited_data != original_data:
                f.seek(0)
                self.storage.write(f, self.name)
            else:
                logger.warning('File not changed. Nothing to write.')


class EnvFile(File):
    def as_dict(self):
        env_dict = {}
        try:
            for line in str(self.read(), 'utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')

                    # Remove any leading and trailing spaces in key, value
                    k, v = k.strip(), v.strip().encode('unicode-escape').decode('ascii')

                    if v and v[0] == v[-1] in ['"', "'"]:
                        v = __escape_decoder(v[1:-1])[0]

                    env_dict[k] = v
        except FileNotFoundError:
            pass
        return env_dict

    def from_dict(self, env_vars):
        file_data = ''
        for var_name, var_value in env_vars.items():
            file_data += '{}={}\n'.format(var_name, var_value)
        self.write(file_data)

    def update(self, another_file):
        env_vars = self.as_dict()
        env_vars.update(another_file.as_dict())
        self.from_dict(env_vars)
