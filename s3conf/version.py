import os
import re
import subprocess

version_re = re.compile('^Version: (.+)$', re.M)


def get_version(repo_path=None):
    repo_path = os.path.abspath(repo_path or os.path.dirname(os.path.dirname(__file__)))
    if os.path.isdir(os.path.join(repo_path, '.git')):
        # Get the version using "git describe".
        cmd = 'git describe --tags --match [0-9]*'.split()
        try:
            version = subprocess.check_output(cmd, cwd=repo_path).decode().strip()
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
            dirty = subprocess.check_output(cmd, cwd=repo_path).decode().strip()
        except subprocess.CalledProcessError:
            print('Unable to get git index status')
            exit(1)

        if dirty != '':
            version += '.dev'
    else:
        try:
            # Extract the version from the PKG-INFO file.
            with open(os.path.join(repo_path, 'PKG-INFO')) as f:
                version = version_re.search(f.read()).group(1)
        except FileNotFoundError:
            import pkg_resources
            version = pkg_resources.require('s3conf')[0].version
    return version
