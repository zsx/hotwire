import os,sys,stat
import pwd,grp

from hotwire.sysdep.fs import BaseFilesystem, File

class UnixFilesystem(BaseFilesystem):
    def __init__(self):
        super(UnixFilesystem, self).__init__()
        
    def _get_conf_dir_path(self):
        return os.path.expanduser('~/.hotwire')

    def get_path_generator(self):
        for d in os.environ['PATH'].split(':'):
            yield d 
    
    def supports_owner(self):
        return True
    
    def supports_group(self):
        return True
        
class UnixFile(File):   
    def get_uid(self):
        return self.stat and self.stat.st_uid
    
    def get_gid(self):
        return self.stat and self.stat.st_gid
    
    def get_file_type_char(self):
        stmode = self.get_mode()
        if stat.S_ISREG(stmode): return '-'
        elif stat.S_ISDIR(stmode): return 'd'
        elif stat.S_ISLNK(stmode): return 'l'
        else: return '?'
    
    def get_owner(self):
        uid = self.get_uid()
        if uid is None:
            return
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError, e:
            return str(uid)

    def get_group(self):
        gid = self.get_gid()
        if gid is None:
            return
        try:
            return grp.getgrgid(gid).gr_name
        except KeyError, e:
            return str(gid)    

def getInstance():
    return UnixFilesystem()
