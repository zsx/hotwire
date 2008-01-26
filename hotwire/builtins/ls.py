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

import os, sys, os.path, stat, logging, locale

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema
from hotwire.fs import FilePath,iterd_sorted
from hotwire.sysdep.fs import Filesystem,File
from hotwire.util import xmap

_logger = logging.getLogger("hotwire.builtins.ls")

class LsBuiltin(Builtin):
    __doc__ = _("""List contents of a directory.""")
    def __init__(self):
        super(LsBuiltin, self).__init__('ls', aliases=['dir'],
                                        input=InputStreamSchema(str, optional=True),
                                        output=File,
                                        idempotent=True,
                                        threaded=True,
                                        options=[['-l', '--long'],['-a', '--all']])

    def __ls_dir(self, dir, show_all):
        fs = Filesystem.getInstance()
        for x in iterd_sorted(dir):
            try:
                if show_all:
                    yield fs.get_file_sync(x)

                else:
                    bn = os.path.basename(x)
                    if not (fs.get_basename_is_ignored(bn)):
                        yield fs.get_file_sync(x)
            except:
                # An exception here should ordinarily only happen on Windows;
                # if we know the path exists because it was returned by
                # listdir(), on Unix the stat() call cannot fail.  
                # See http://code.google.com/p/hotwire-shell/issues/detail?id=126
                _logger.debug("Failed to stat %r", x, exc_info=True)
                pass

    def execute(self, context, args, options=[]):
        show_all = '-a' in options
        long_fmt = '-l' in options
            
        fs = Filesystem.getInstance()            
            
        if len(args) == 0:
            generator = self.__ls_dir(context.cwd, show_all)
        elif len(args) == 1:
            path = FilePath(args[0], context.cwd)
            fobj = fs.get_file_sync(path)
            if fobj.is_directory:
                generator = self.__ls_dir(path, show_all)
            else:
                yield fobj
                return      
        else:
            generator = sorted(xmap(lambda arg: fs.get_file_sync(FilePath(arg, context.cwd)), args), 
                               lambda a,b: locale.strcoll(a.path, b.path))
        for x in generator:
            yield x
BuiltinRegistry.getInstance().register(LsBuiltin())
