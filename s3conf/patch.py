import os

import editor
from editor import get_editor
from editor import get_editor_args
import shlex


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
