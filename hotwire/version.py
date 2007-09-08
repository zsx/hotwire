__version__ = '0.590'

def svn_version_str():
    if not svn_version_info:
        return ''
    return '(%s  %s)' % (svn_version_info['Revision'], svn_version_info['Last Changed Date'])

# Default to empty
svn_version_info = None
