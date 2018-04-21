import os
import logging

logger = logging.getLogger(__name__)


def prepare_path(file_target):
    # as the path might not exist, we can not test if it is a dir beforehand
    # therefore, if it ends with a / it is considered a dir, otherwise, it is a regular file
    # and the following code works for both cases
    os.makedirs(os.path.abspath(file_target.rpartition('/')[0]), exist_ok=True)

