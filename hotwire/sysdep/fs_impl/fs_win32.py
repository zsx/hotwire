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

import os,sys,subprocess

from hotwire.fs import path_normalize
from hotwire.sysdep.fs import File, BaseFilesystem
from hotwire.sysdep.win32 import win_exec_re

# TODO - implement native "Recycle Bin" trash functionality.
# involves lots of hackery with shellapi
class Win32Filesystem(BaseFilesystem):
    def __init__(self):
        super(Win32Filesystem, self).__init__()
        self.fileklass = Win32File
            
    def _get_conf_dir_path(self):
        return os.path.expanduser(u'~/Application Data/hotwire')

    def get_path_generator(self):
        for d in os.environ['PATH'].split(';'):
            # On Windows, the PATH variable is encoded, we need to turn it into Unicode.
            dpath = unicode(d, sys.getfilesystemencoding())
            yield path_normalize(dpath)

    def path_inexact_executable_match(self, path):
        return win_exec_re.search(path)
    
class Win32File(File):
    def __init__(self, *args, **kwargs):
        super(Win32File, self).__init__(*args, **kwargs)
        
    def _do_get_xaccess(self):
        super(Win32File, self)._do_get_xaccess()
        self.xaccess = self.xaccess and win_exec_re.search(self.path)

def getInstance():
    return Win32Filesystem()
