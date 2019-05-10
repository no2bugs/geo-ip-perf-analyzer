import os


def exists(fle):
    return True if os.path.isfile(fle) else False
