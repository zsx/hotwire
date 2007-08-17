import os,sys,ConfigParser

import hotwire
from hotwire.singletonmixin import Singleton

class Config(Singleton):
    def __init__(self):
        self._config = ConfigParser.SafeConfigParser()
        self._config.read(['hotwire.ini', os.path.expanduser('~/.hotwire/hotwire.ini')])

    def _get(self, section, name):
        try:
            return (self._config.get(section, name) or '')
        except ConfigParser.NoSectionError, e:
            return None

    def get_command_autoterm(self):
        return (self._get('command', 'autoterm') or '').split(',')
