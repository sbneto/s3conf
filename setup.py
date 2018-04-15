#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
from setuptools import setup


name = 's3conf'
package = 's3conf'
description = 'Utility package to help managing configuration files stored in S3-like services.'
url = 'https://github.com/sbneto/s3conf'
author = 'Samuel Martins Barbosa Neto'
author_email = 'samuel.m.b.neto@gmail.com'
license_ = 'MIT'


def get_packages(package):
    """
    Return root package and all sub-packages.
    """
    return [dirpath
            for dirpath, dirnames, filenames in os.walk(package)
            if os.path.exists(os.path.join(dirpath, '__init__.py'))]


def get_package_data(package):
    """
    Return all files under the root package, that are not in a
    package themselves.
    """
    walk = [(dirpath.replace(package + os.sep, '', 1), filenames)
            for dirpath, dirnames, filenames in os.walk(package)
            if not os.path.exists(os.path.join(dirpath, '__init__.py'))]

    filepaths = []
    for base, filenames in walk:
        filepaths.extend([os.path.join(base, filename)
                          for filename in filenames])
    return {package: filepaths}


with open('s3conf/version.py') as f:
    exec(f.read())
version = get_version(repo_path=os.path.dirname(__file__))

if sys.argv[-1] == 'publish':
    if os.system("pip freeze | grep wheel"):
        print("wheel not installed.\nUse `pip install wheel`.\nExiting.")
        sys.exit()
    os.system("python setup.py sdist upload")
    os.system("python setup.py bdist_wheel upload")
    print("You probably want to also tag the version now:")
    print("  git tag -a {0} -m 'version {0}'".format(version))
    print("  git push --tags")
    sys.exit()


setup(
    name=name,
    version=version,
    url=url,
    license=license_,
    description=description,
    long_description=open('README.md').read(),
    author=author,
    author_email=author_email,
    packages=get_packages(package),
    package_data=get_package_data(package),
    install_requires=[
        'boto3>=1.4.4',
        'click>=6.7',
        'python-editor>=1.0.3',
        'click-log>=0.2.1',
    ],
    python_requires='~=3.5',
    setup_requires=[],
    tests_require=['pytest', 'pytest-cov'],
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    entry_points='''
    [console_scripts]
    s3conf=s3conf.client:main
    ''',
)
