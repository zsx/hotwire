__version__ = '0.590'

def hg_version_str():
    if not hg_version_info:
        return ''
    return '(%s  %s)' % (hg_version_info['changeset'], hg_version_info['date'])

# Default to empty
hg_version_info = None
