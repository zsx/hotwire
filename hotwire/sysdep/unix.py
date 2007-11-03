import os

os.environ['HOTWIRE_SHELL'] = '1'

# Ensure subprocesses don't try to treat us as a full tty
os.environ['TERM'] = 'dumb'
# Fix Fedora and probably other systems
standard_admin_paths = ['/sbin', '/usr/sbin']
path_elts = os.environ['PATH'].split(':')  
path_fixed = False
for path in standard_admin_paths:
    if not path in path_elts:
        path_fixed = True
        path_elts.append(path)
if path_fixed:
    os.environ['PATH'] = ':'.join(path_elts)

