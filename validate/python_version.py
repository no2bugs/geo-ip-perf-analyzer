import sys
from format.colors import Format

req_v = 3

formatting = Format()

current_ver = float(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))
try:
    if not 1 < float(req_v) < 4:
        raise ValueError('Error: You are requiring invalid Python version ' + str(req_v))
except ValueError as e:
    print(e)
    sys.exit(1)
if current_ver < req_v:
    formatting.output('bold', 'red')
    print('Error: Python version ' + str(req_v) + ' is required')
    print('You are using {0}.{1}.{2} {3}'.format(sys.version_info[0],
                                                 sys.version_info[1],
                                                 sys.version_info[2],
                                                 sys.version_info[3]))
    formatting.output('reset')
    sys.exit(1)
