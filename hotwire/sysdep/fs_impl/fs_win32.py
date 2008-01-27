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

import os,sys,subprocess,logging

from hotwire.fs import path_normalize
from hotwire.sysdep.fs import File, BaseFilesystem,iterd_sorted
from hotwire.sysdep.win32 import win_exec_re
import win32api, win32con

_logger = logging.getLogger("hotwire.sysdep.Win32Filesystem")

# TODO - implement native "Recycle Bin" trash functionality.
# involves lots of hackery with shellapi
class Win32Filesystem(BaseFilesystem):
    def __init__(self):
        super(Win32Filesystem, self).__init__()
        self.fileklass = Win32File

    def ls_dir(self, dir, show_all):
        for x in iterd_sorted(dir):
            try:
                if show_all:
                    yield self.get_file_sync(x)
                else:
                    if not (win32api.GetFileAttributes(x)
                            & win32con.FILE_ATTRIBUTE_HIDDEN):
                        yield self.get_file_sync(x)
            except:
                # An exception here can happen on Windows if the file was in
                # use.
                # See http://code.google.com/p/hotwire-shell/issues/detail?id=126
                _logger.debug("Failed to stat %r", x, exc_info=True)
                pass

    def _get_conf_dir_path(self):
        return os.path.expanduser(u'~/Application Data/hotwire')

    def get_path_generator(self):
        pathenv = os.environ['PATH']
        # TODO - what encoding is PATHENV in? 
        for d in pathenv.split(u';'):
            yield d
        
    def get_basename_is_ignored(self, bn):
        # FIXME - extend this to use Windows systems
        return False        

    def path_inexact_executable_match(self, path):
        return win_exec_re.search(path)

    def launch_open_file(self, path, cwd=None):
        try:
            win32api.ShellExecute(0, "open", path, None, None, 1)
        except:
            raise NotImplementedError()
    
class Win32File(File):
    def __init__(self, *args, **kwargs):
        super(Win32File, self).__init__(*args, **kwargs)
        
    def _do_get_xaccess(self):
        super(Win32File, self)._do_get_xaccess()
        self.xaccess = self.xaccess and win_exec_re.search(self.path)

    def _do_get_hidden(self):
        self._hidden = win32api.GetFileAttributes(self.path) & win32con.FILE_ATTRIBUTE_HIDDEN

def getInstance():
    return Win32Filesystem()
