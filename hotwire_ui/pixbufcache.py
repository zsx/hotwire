import os,sys,logging

import gtk

from hotwire.singletonmixin import Singleton
from hotwire.async import MiniThreadPool

def _get_datadirs():
    datadir_env = os.getenv('XDG_DATA_DIRS')
    if datadir_env:
        datadirs = datadir_env.split(':')
    else:
        datadirs = ['/usr/share/']
    for d in datadirs:
        yield os.path.join(d, 'hotwire')
    uninst = os.getenv('HOTWIRE_UNINSTALLED') 
    if uninst:
        yield uninst

def _find_in_datadir(fname):
    datadirs = _get_datadirs()
    for dir in datadirs:
        fpath = os.path.join(dir, fname)
        if os.access(fpath, os.R_OK):
            return fpath
    return None

class PixbufCache(Singleton):
    def __init__(self):
        super(PixbufCache, self).__init__()
        self.__cache = {}

    def get(self, path, size=24, animation=False):
        if not os.path.isabs(path):
            path = _find_in_datadir(path)
        if not path:
            return None        
        if not self.__cache.has_key(path):
            pixbuf = self.__do_load(path, size, animation)
            self.__cache[path] = pixbuf
        return self.__cache[path]

    def __do_load(self, path, size, animation):
        f = open(path, 'rb')
        data = f.read()
        f.close()
        loader = gtk.gdk.PixbufLoader()
        if size:
            loader.set_size(size, size)
        loader.write(data)
        loader.close()
        if animation:
            return loader.get_animation()
        return loader.get_pixbuf()
