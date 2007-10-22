# -*- tab-width: 4; indent-tabs-mode: nil -*-
import os, sys, fnmatch, stat, shutil

import hotwire
from hotwire.async import MiniThreadPool
from hotwire.iterdir import iterdir
import hotwire.glob2

def dirglob(dir, pat):
    for result in hotwire.glob2.iglob(pat, dir):
        yield result

_sep_len = len(os.sep)
def unix_basename(path):
    if path.endswith(os.sep):
        path = path[:-_sep_len]
    return os.path.basename(path)

def path_unexpanduser(path):
    homepath = os.path.expanduser("~")
    # Don't unexpand ~ because it looks plain and ugly
    if (path != homepath) and path.startswith(homepath):
        path = '~' + path[len(homepath):]
    return path

def copy_file_or_dir(src, dest, dest_is_dir):
    stbuf = os.stat(src) 
    dest_target = dest_is_dir and os.path.join(dest, unix_basename(src)) or dest
    if src == dest_target:
        return
    if stat.S_ISDIR(stbuf.st_mode):
        shutil.copytree(src, dest_target)
    elif stat.S_ISLNK(stbuf.st_mode):
        symtarget = os.readlink(src)
        os.symlink(dest_target, symtarget)
    else:
        shutil.copy(src, dest_target)

def file_is_valid_utf8(path):
    f = open(path, 'rb')
    buf = f.read(8192)
    # is there a faster way
    try:
        unicode(buf, 'utf-8').encode('utf-8')
    except UnicodeDecodeError, e:
        f.close()
        return False
    f.close()
    return True

class FilePath(str):
    """Represents a path to a file; can be treated as a string.
       This class should have been built into Python."""
    def __new__(cls, value, dir=None):
        if not os.path.isabs(value) and dir:
            value = os.path.join(dir, value) 
        inst = super(FilePath, cls).__new__(cls, value)
        return inst

    def path_join(self, path):
        return os.path.join(self, path)

class DirectoryGenerator(object):
    def __init__(self, dir):
        self.__dir = dir

    def get_dir(self):
        return self.__dir

    def __iter__(self):
        for name in iterdir(self.__dir):
            yield FilePath(os.path.join(self.__dir, name))
