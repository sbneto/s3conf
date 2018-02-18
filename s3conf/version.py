import os
import sys
import subprocess


def get_version():
    d = os.path.dirname(os.path.dirname(__file__))

    if os.path.isdir(os.path.join(d, '.git')):
        # Get the version using "git describe".
        cmd = 'git describe --tags --match [0-9]*'.split()
        try:
            version = subprocess.check_output(cmd).decode().strip()
        except subprocess.CalledProcessError:
            print('Unable to get version number from git tags')
            exit(1)

        # Don't declare a version "dirty" merely because a time stamp has
        # changed. If it is dirty, append a ".dev" suffix to indicate a
        # development revision after the release.
        with open(os.devnull, 'w') as fd_devnull:
            subprocess.call(['git', 'status'],
                            stdout=fd_devnull, stderr=fd_devnull)

        cmd = 'git diff-index --name-only HEAD'.split()
        try:
            dirty = subprocess.check_output(cmd).decode().strip()
        except subprocess.CalledProcessError:
            print('Unable to get git index status')
            exit(1)

        if dirty != '':
            version += '.dev'

    else:
        import pkg_resources
        module = sys._getframe(1).f_globals.get('__name__')
        version = pkg_resources.require(module)[0].version
    return version
