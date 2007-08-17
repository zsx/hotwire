import logging

import gtk

from hotwire.singletonmixin import Singleton
from hotwire.async import MiniThreadPool

class PixbufCache(Singleton):
    def __init__(self):
        super(PixbufCache, self).__init__()
        self.__cache = {}

    def get(self, path, size=24):
        if not self.__cache.has_key(path):
            pixbuf = self.__do_load(path, size)
            self.__cache[path] = pixbuf
        return self.__cache[path]

    def __do_load(self, path, size):
        f = open(path, 'rb')
        data = f.read()
        f.close()
        loader = gtk.gdk.PixbufLoader()
        loader.set_size(size, size)
        loader.write(data)
        loader.close()
        return loader.get_pixbuf()
        
