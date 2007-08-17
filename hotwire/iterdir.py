import dircache

def iterdir(path):
    """Create an iterable for directory contents."""
    return dircache.listdir(path)
