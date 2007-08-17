# -*- tab-width: 4 -*-
import os,sys,re,stat,logging

from hotwire.persist import Persister
from hotwire.singletonmixin import Singleton

_logger = logging.getLogger("hotwire.CmdAlias")

default_aliases = {'vi': 'term vi',
                   'ssh': 'term ssh',
                   'man': 'term man',
                   'top': 'term top',
                   'nano': 'term nano',
                   'pico': 'term pico'}

class AliasRegistry(Singleton):
    def __init__(self):
        self.__aliases = Persister.getInstance().load('aliases', default=default_aliases) 

    def remove(self, name):
        del self.__aliases.get(lock=True)[name]
        self.__aliases.save()

    def __getitem__(self, item):
        return self.__aliases.get()[item]

    def __iter__(self):
        for x in self.__aliases.get().iterkeys():
            yield x
    
