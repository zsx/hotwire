import platform

# These files are the right place to do global, platform-specific early
# initialization and share code between different components in this tree.
if platform.system() == 'Linux':
    import hotwire.sysdep.unix
elif platform.system() == 'Windows':
    import hotwire.sysdep.win32
