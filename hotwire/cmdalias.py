# -*- tab-width: 4 -*-
import os,sys,re,stat,logging

from hotwire.singletonmixin import Singleton

_logger = logging.getLogger("hotwire.CmdAlias")

## TODO: Kill this class in favor of better autoterm integration.

class AliasRegistry(Singleton):
    def __init__(self):
        self.__aliases = {}

    def remove(self, name):
        del self.__aliases[name]
    
    def insert(self, name, value):
        self.__aliases[name] = value

    def __getitem__(self, item):
        return self.__aliases[item]

    def __iter__(self):
        for x in self.__aliases.iterkeys():
            yield x
    
