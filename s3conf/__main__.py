import os
import sys
from .client import main as _main


def main():
    # fixing the name of the entrypoint when the module is executed as
    # python -m s3conf
    # https://docs.python.org/3/library/__main__.html
    entrypoint_name = os.path.basename(sys.argv[0])
    if entrypoint_name == '__main__.py':
        entrypoint_name = 's3conf'

    _main(prog_name=entrypoint_name)


if __name__ == '__main__':
    main()
