# This file is part of the Hotwire Shell project API.

# Copyright (C) 2007 Colin Walters <walters@verbum.org>

# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies 
# of the Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all 
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE 
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR 
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os,sys,logging,time,datetime
if sys.version_info[0] < 2 or sys.version_info[1] < 5:
    from pysqlite2 import dbapi2 as sqlite3
else:    
    import sqlite3

import gobject

from hotwire.externals.singletonmixin import Singleton
from hotwire.sysdep.fs import Filesystem
from hotwire.persist import Persister
from hotwire.usagerecord import UsageRecord
#import processing

_logger = logging.getLogger("hotwire.State")

def _get_state_path(name):
    dirname = Filesystem.getInstance().make_conf_subdir('state')
    return os.path.join(dirname, name)

class History(Singleton):
    def __init__(self):
        super(History, self).__init__()
        self.__no_save = False
        path = _get_state_path('history.sqlite')
        _logger.debug("opening connection to history db: %s", path)
        self.__conn = sqlite3.connect(path, isolation_level=None)
        cursor = self.__conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS Commands (dbid INTEGER PRIMARY KEY AUTOINCREMENT, cmd TEXT, exectime DATETIME, dirpath TEXT)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS CommandsIndex on Commands (cmd)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Autoterm (dbid INTEGER PRIMARY KEY AUTOINCREMENT, cmd TEXT UNIQUE, modtime DATETIME)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Directories (dbid INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, count INTEGER, modtime DATETIME)''')  
        cursor.execute('''CREATE TABLE IF NOT EXISTS Tokens (dbid INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE, count INTEGER, modtime DATETIME)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS CmdInput (dbid INTEGER PRIMARY KEY AUTOINCREMENT, cmd TEXT, line TEXT, modtime DATETIME)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS CmdInputIndex on CmdInput (cmd, line, modtime)''')        
        cursor.execute('''CREATE TABLE IF NOT EXISTS Meta (keyName TEXT UNIQUE, keyValue)''')
        self.__convert_from_persist('history', 'Commands', '(NULL, ?, 0, NULL)')
        self.__convert_from_persist('autoterm', 'Autoterm', '(NULL, ?, 0)')
        freqconvert = lambda x: (x[0], x[1].freq, x[1].usetime)
        self.__convert_from_persist('cwd_history', 'Directories', '(NULL, ?, ?, ?)', freqconvert)
        self.__convert_from_persist('token_history', 'Tokens', '(NULL, ?, ?, ?)', freqconvert) 
        
    def set_no_save(self):
        self.__no_save = True       
        
    def __convert_from_persist(self, persistkey, tablename, valuefmt, mapfunc=lambda x: (x,)):
        cursor = self.__conn.cursor()
        conversion_key = 'persist%sConverted' % (persistkey,)
        cursor.execute('''BEGIN TRANSACTION''')
        result = cursor.execute('''SELECT keyValue FROM Meta WHERE keyName=?''', [conversion_key]).fetchone()
        if not result:
            cursor.execute('''INSERT INTO Meta VALUES (?, ?)''', [conversion_key, datetime.datetime.now()])
        else:
            _logger.debug("conversion already complete for key %s", conversion_key)        
            cursor.execute('''COMMIT''')
            return 
        oldhistory = Persister.getInstance().load(persistkey, default=None).get()
        if oldhistory:
            _logger.debug("performing conversion on persisted state %s: %s", conversion_key, oldhistory)
            query = '''INSERT INTO %s VALUES %s''' % (tablename, valuefmt,)
            for item in oldhistory:
                cursor.execute(query, mapfunc(item))
        else:
            _logger.debug("no previous data to convert")
        cursor.execute('''COMMIT''')
        _logger.debug("conversion successful")        

    def append_command(self, cmd, cwd):
        if self.__no_save:
            return
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        vals = (cmd, datetime.datetime.now(), cwd)
        _logger.debug("doing insert of %s", vals)
        cursor.execute('''INSERT INTO Commands VALUES (NULL, ?, ?, ?)''', vals)
        cursor.execute('''COMMIT''')
        
    def __search_limit_query(self, tablename, column, orderval, searchterm, limit, countmin=0, filters=[], distinct=False):
        queryclauses = []
        args = []        
        if searchterm:
            queryclauses.append(column + " LIKE ? ESCAPE '%'")
            args.append('%' + searchterm.replace('%', '%%') + '%')            
        if countmin > 0:
            queryclauses.append("count > %d " % (countmin,))
        queryclauses.extend(map(lambda x: x[0], filters))
        args.extend(map(lambda x: x[1], filters))
        if queryclauses:
            queryclause = ' WHERE ' + ' AND '.join(queryclauses)
        else:
            queryclause = ''
        sql = ((('SELECT %s * FROM %s' % (distinct and 'DISTINCT' or '', tablename,)) + queryclause + 
                  (' ORDER BY %s DESC LIMIT %d' % (orderval, limit,))),
                args)
        _logger.debug("generated search query: %s", sql)
        return sql
        
    def search_commands(self, searchterm, limit=20, **kwargs):
        cursor = self.__conn.cursor()
        (sql, args) = self.__search_limit_query('Commands', 'cmd', 'exectime', searchterm, limit, **kwargs)         
        _logger.debug("execute using args %s: %s", args, sql)
        for v in cursor.execute(sql, args):
            yield v[1]  
        
    def set_autoterm(self, cmdname, is_autoterm):
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        if is_autoterm:
            cursor.execute('''INSERT OR REPLACE INTO Autoterm VALUES (NULL, ?, ?)''', [cmdname, datetime.datetime.now()])
        else:
            cursor.execute('''DELETE FROM Autoterm WHERE cmd = ?''', [cmdname])
        cursor.execute('''COMMIT''')
        
    def get_autoterm_cmds(self):
        cursor = self.__conn.cursor()        
        for v in cursor.execute('''SELECT cmd from Autoterm'''):
            yield v[0]
        
    def __append_countitem(self, tablename, colname, value):
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        cursor.execute('''SELECT * FROM %s WHERE %s = ?''' % (tablename, colname), (value,))
        result = cursor.fetchone()
        if not result:
            current_count = 0
        else:
            current_count = result[2]
        _logger.debug("incrementing count %s", current_count)
        vals = (value, current_count+1, datetime.datetime.now())
        _logger.debug("doing insert of %s", vals)
        cursor.execute('''INSERT OR REPLACE INTO %s VALUES (NULL, ?, ?, ?)''' % (tablename,), vals)
        cursor.execute('''COMMIT''')
        
    def append_dir_usage(self, path):
        self.__append_countitem('Directories', 'path', path)
        
    def search_dir_usage(self, searchterm, limit=20):
        cursor = self.__conn.cursor()
        (sql, args) = self.__search_limit_query('Directories', 'path', 'count', searchterm, limit, countmin=4)
        for v in cursor.execute(sql, args):
            yield v[1:]
        
    def append_token_usage(self, text):
        self.__append_countitem('Tokens', 'token', text)        

    def search_token_usage(self, searchterm, limit=20):
        cursor = self.__conn.cursor()
        (sql, args) = self.__search_limit_query('Tokens', 'token', 'count', searchterm, limit, countmin=2)
        for v in cursor.execute(sql, args):
            yield v[1:]
        
    def append_usage(self, colkey, *args, **kwargs):
        getattr(self, 'append_%s_usage' % (colkey,))(*args, **kwargs)
        
    def search_usage(self, colkey, *args, **kwargs):
        return getattr(self, 'search_%s_usage' % (colkey,))(*args, **kwargs)        
        
    def record_pipeline(self, cwd, pipeline):
        if self.__no_save:
            return
        self.append_dir_usage(cwd)

    def search_command_input(self, cmd, searchterm, limit=20):
        cursor = self.__conn.cursor()
        (sql, args) = self.__search_limit_query('CmdInput', 'line', 'modtime', searchterm, limit,
                                                filters=[('cmd = ?', cmd)])         
        _logger.debug("execute using args %s: %s", args, sql)
        for v in cursor.execute(sql, args):
            yield v[2]
        
    def record_command_input(self, cmd, input):
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        vals = (cmd, input, datetime.datetime.now())
        _logger.debug("doing insert of %s", vals)
        cursor.execute('''INSERT INTO CmdInput VALUES (NULL, ?, ?, ?)''', vals)
        cursor.execute('''COMMIT''')
    
_prefinstance = None
class Preferences(gobject.GObject):
    def __init__(self):
        super(Preferences, self).__init__()
        path = _get_state_path('prefs.sqlite')
        _logger.debug("opening connection to prefs db: %s", path)
        self.__conn = sqlite3.connect(path, isolation_level=None)
        self.__monitors = []
        
        cursor = self.__conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS Prefs (dbid INTEGER PRIMARY KEY AUTOINCREMENT, keyName TEXT UNIQUE, keyValue, modtime DATETIME)''')
 
    def get_pref(self, key, default=None):
        cursor = self.__conn.cursor()        
        result = cursor.execute('''SELECT keyValue from Prefs where keyName = ?''', (key,)).fetchone()
        if result is None:
            return default
        return result[0]
 
    def set_pref(self, key, value):
        (root, other) = key.split('.', 1)
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        cursor.execute('''INSERT OR REPLACE INTO Prefs VALUES (NULL, ?, ?, ?)''', [key, value, datetime.datetime.now()])
        cursor.execute('''COMMIT''')
        self.__notify(key, value)
        
    def __notify(self, key, value):
        _logger.debug("doing notify for key %s new value: %s", key, value)
        for prefix, handler, args in self.__monitors:
            if key.startswith(prefix):
                try:
                    handler(self, key, value, *args)
                except:
                    _logger.error('Failed to invoke handler for preference %s', key, exc_info=True)
    
    def monitor_prefs(self, prefix, handler, *args):
        self.__monitors.append((prefix, handler, args))
    
    @staticmethod
    def getInstance():
        global _prefinstance
        if _prefinstance is None:
            _prefinstance = Preferences()
        return _prefinstance
    
__all__ = ['History','Preferences']      
