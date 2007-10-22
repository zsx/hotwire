# -*- tab-width: 4 -*-
import os,sys,re,stat,logging

from hotwire.singletonmixin import Singleton

_logger = logging.getLogger("hotwire.CmdAlias")

default_aliases = {'vi': 'term vi',
                   'vim': 'term vim',
                   'ssh': 'term ssh',
                   'man': 'term man',
                   'top': 'term top',
                   'nano': 'term nano',
                   'pico': 'term pico'}

## TODO: Kill this class in favor of better autoterm integration.

class AliasRegistry(Singleton):
    def __init__(self):
        self.__aliases = default_aliases

    def remove(self, name):
        raise NotImplementedError()

    def __getitem__(self, item):
        return self.__aliases[item]

    def __iter__(self):
        for x in self.__aliases.iterkeys():
            yield x
    
