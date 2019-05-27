import os
import logging
import shlex

import editor
import click
from editor import get_editor, get_editor_args
from click_log import core

import warnings

# https://github.com/googleapis/google-auth-library-python/issues/271
warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")

# apply patches that allow editor with args
# https://github.com/fmoo/python-editor/pull/15
def _get_editor():
    executable = get_editor()
    return shlex.split(executable)[0]


def _get_editor_args(editor):
    args = get_editor_args(editor)
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor:
        args = shlex.split(editor)[1:] + args
    return args


editor.get_editor = _get_editor
editor.get_editor_args = _get_editor_args


# Creating our own handler class that always uses stderr to output logs.
# This way, we can avoid mixing logging information with actual output from
# the command line client.
class MyClickHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            click.echo(msg, err=True)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


core._default_handler = MyClickHandler()
core._default_handler.formatter = core.ColorFormatter()

# adding color to INFO log messages as well
core.ColorFormatter.colors['info'] = dict(fg='green')


# Solving 2 year old boto issue regarding empty file uploads
# https://github.com/boto/botocore/pull/1328
try:
    from botocore.awsrequest import AWSConnection
    _original_send_request = AWSConnection._send_request


    def _new_send_request(self, method, url, body, headers, *args, **kwargs):
        if headers.get('Content-Length') == '0':
            # From RFC: https://tools.ietf.org/html/rfc7231#section-5.1.1
            # Requirement for clients:
            # - A client MUST NOT generate a 100-continue expectation
            #   in a request that does not include a message body.
            headers.pop('Expect', None)
        return _original_send_request(self, method, url, body, headers, *args, **kwargs)


    AWSConnection._send_request = _new_send_request
except ImportError:
    pass
