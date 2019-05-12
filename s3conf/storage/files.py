import functools
import logging
from tempfile import NamedTemporaryFile

from . import exceptions


logger = logging.getLogger(__name__)


class File:
    def __init__(self, name, storage, mode='r', encoding=None):
        if 'x' in mode:
            raise ValueError('Exclusive creation not supported yet.')
        self.name = name
        self.storage = storage
        self.mode = mode
        self.encoding = encoding
        self._buffer = None
        self._file = None

    def _sync_with_storage(self):
        if 'w' not in self.mode:
            try:
                self._buffer.seek(0)
                self._buffer.truncate()
                self.storage.read_into_stream(self.name, self._buffer)
            except exceptions.FileDoesNotExist:
                self.file.close()
                raise

    # IOBase
    def flush(self) -> None:
        self.file.flush()
        self._buffer.seek(0)
        logger.debug('Writing buffer to %s', self.name)
        self.storage.write(self._buffer, self.name)

    # IOBase
    def close(self) -> None:
        if not self.closed:
            self.flush()
            self.file.close()
            self._buffer.close()

    @property
    def file(self):
        if self._file is None:
            self._buffer = NamedTemporaryFile()
            self._file = open(self._buffer.name, mode=self.mode, encoding=self.encoding)
            self._sync_with_storage()
        return self._file

    # Inspired by
    # https://github.com/python/cpython/blob/29500737d45cbca9604d9ce845fb2acc3f531401/Lib/tempfile.py#L461
    def __getattr__(self, name):
        # Attribute lookups are delegated to the underlying file
        # and cached for non-numeric results
        # (i.e. methods are cached, closed and friends are not)
        a = getattr(self.file, name)
        if hasattr(a, '__call__'):
            func = a
            @functools.wraps(func)
            def func_wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            a = func_wrapper
        if not isinstance(a, int):
            setattr(self, name, a)
        return a

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        self.close()

    # IOBase
    def fileno(self) -> int:
        raise OSError()
