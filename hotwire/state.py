import os,sys,logging,sqlite3,time,datetime

from hotwire.singletonmixin import Singleton
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
        path = _get_state_path('history.sqlite')
        _logger.debug("opening connection to history db: %s", path)
        self.__conn = sqlite3.connect(path, isolation_level=None)
        cursor = self.__conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS Commands (cmd text, exectime datetime, dirpath text)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS CommandsIndex on Commands (cmd)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Meta (keyName text, keyValue)''')
        cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS MetaKeyIndex on Meta (keyName)''')
        self.__convert_from_persist()              
        
    def __convert_from_persist(self):
        cursor = self.__conn.cursor()
        conversion_key = 'persistHistoryConverted'
        cursor.execute('''BEGIN TRANSACTION''')
        result = cursor.execute('''SELECT keyValue FROM Meta WHERE keyName=?''', [conversion_key]).fetchone()
        if not result:
            cursor.execute('''INSERT INTO Meta VALUES (?, ?)''', [conversion_key, datetime.datetime.now()])
        else:
            _logger.debug("persist conversion already complete")        
            return 
        oldhistory = Persister.getInstance().load('history', default=[]).get()
        _logger.debug("performing conversion on old persisted history: %d entries", len(oldhistory))
        for item in oldhistory:
            cursor.execute('''INSERT INTO Commands VALUES (?, 0, NULL)''', (item,))
        cursor.execute('''COMMIT''')
        _logger.debug("conversion successful")        

    def append_command(self, cmd, cwd):
        cursor = self.__conn.cursor()
        cursor.execute('''BEGIN TRANSACTION''')
        vals = (cmd, datetime.datetime.now(), cwd)
        _logger.debug("doing insert of %s", vals)
        cursor.execute('''INSERT INTO Commands VALUES (?, ?, ?)''', vals)
        cursor.execute('''COMMIT''')  

    def search_commands(self, searchterm, limit=20):
        cursor = self.__conn.cursor()
        queryclause = ''' WHERE cmd LIKE ? ESCAPE '%' '''
        args = []
        if searchterm: args.append('%' + searchterm.replace('%', '%%') + '%')
        sql = ('''SELECT cmd FROM Commands''' +
                               (searchterm and queryclause or '') + 
                                '''ORDER BY exectime LIMIT %d''' % (limit,))
        _logger.debug("execute using args %s: %s", args, sql)
        for v in cursor.execute(sql, args):
            yield v[0]
    

class VerbCompletionData(Singleton):
    def __init__(self):
        self.autoterm = Persister.getInstance().load('autoterm', default=set()) 

    def note_autoterm(self, cmdname, is_autoterm):
        autoterm = self.autoterm.get(lock=True)
        if is_autoterm:
            autoterm.add(cmdname)
        elif (not is_autoterm) and (cmdname in autoterm):
            autoterm.remove(cmdname)
        self.autoterm.save()    
    
class CompletionRecord(Singleton):
    def __init__(self):
        super(CompletionRecord, self).__init__()
        self.__token_history = Persister.getInstance().load('token_history', default=UsageRecord())
        self.__cwd_history = Persister.getInstance().load('cwd_history', default=UsageRecord())
        
    def record(self, cwd, pipeline_tree):
        vd = VerbCompletionData.getInstance()
        self.__cwd_history.get(lock=True).record(cwd)
        self.__cwd_history.save()
        for cmd in pipeline_tree:
            verb = cmd[0]
            if verb.text in ('term', 'sh') and len(cmd) > 1:
                vd.note_autoterm(os.path.basename(cmd[1].text), verb.text == 'term')

            token_appended = False
            tokenhist = self.__token_history.get(lock=True)
            for arg in cmd[1:]:
                tokenhist.record(arg.text)
                token_appended = True
            if token_appended:
                self.__token_history.save()
            else:
                self.__token_history.unlock()
    
__all__ = ['History', 'CompletionRecord']      