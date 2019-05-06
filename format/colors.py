import sys


def output(*options):
    choices = []

    formats = {
        'WHITE': "\033[0;97m",
        'RED': "\033[0;31m",
        'BLUE': "\033[0;34m",
        'CYAN': "\033[0;36m",
        'GREEN': "\033[0;32m",
        'YELLOW': "\033[0;33m",
        'BOLD': "\033[;1m",
        'REVERSE': "\033[;7m",
        'RESET': "\033[0m"
    }

    for item in options:
        item = str(item).upper()
        try:
            choices.append(formats[item])
        except KeyError:
            print('\nError: unknown format choice', item)
            print('Pick from:')
            for i in formats:
                print('-', i)
            sys.exit(1)

    formatting = ''.join(choices)

    sys.stdout.write(formatting)

    return formatting