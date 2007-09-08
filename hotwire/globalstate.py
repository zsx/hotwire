import os,sys, logging

from hotwire.singletonmixin import Singleton

_logger = logging.getLogger("hotwire.Persist")

class Global(object):
    __slots__ = ['name', '__obj']
    def __init__(self, name, obj):
        self.name = name
        self.__obj = obj
    
    def get(self):
        return self.__obj

class GlobalState(Singleton):
    """Stores named objects which are transient to the session"""
    def __init__(self):
        self.__globals = {}

    def get(self, name, default=None):
        try:
            return self.__globals[name]
        except KeyError, e:
            if default is None:
                raise e
        g = Global(name, default)
        self.__globals[name] = g
        return g
