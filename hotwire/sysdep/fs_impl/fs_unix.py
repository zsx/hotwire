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

import os,sys,stat
import pwd,grp

from hotwire.sysdep.fs import BaseFilesystem, File
from hotwire.sysdep.unix import getpwuid_cached, getgrgid_cached

class UnixFilesystem(BaseFilesystem):
    def __init__(self):
        super(UnixFilesystem, self).__init__()
        
    def get_file(self, path):
        fobj = UnixFile(path)
        fobj.get_stat()
        return fobj           
        
    def _get_conf_dir_path(self):
        return os.path.expanduser('~/.hotwire')

    def _get_system_conf_dir_path(self):
        return '/etc/hotwire'

    def get_path_generator(self):
        for d in os.environ['PATH'].split(':'):
            yield d 
    
    def supports_owner(self):
        return True
    
    def supports_group(self):
        return True
        
class UnixFile(File): 
    def __init__(self, *args, **kwargs):
        super(UnixFile, self).__init__(*args, **kwargs)
  
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
            return getpwuid_cached(uid).pw_name
        except KeyError, e:
            return str(uid)

    def get_group(self):
        gid = self.get_gid()
        if gid is None:
            return
        try:
            return getgrgid_cached(gid).gr_name
        except KeyError, e:
            return str(gid)         

def getInstance():
    return UnixFilesystem()
