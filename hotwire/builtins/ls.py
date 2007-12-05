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

import os, os.path, stat, logging, locale

from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema
from hotwire.fs import FilePath,DirectoryGenerator
from hotwire.sysdep.fs import Filesystem
from hotwire.util import xmap

_logger = logging.getLogger("hotwire.builtins.ls")

class LsBuiltin(Builtin):
    __doc__ = _("""List contents of a directory.""")
    def __init__(self):
        super(LsBuiltin, self).__init__('ls', aliases=['dir'],
                                        input=InputStreamSchema(str, optional=True),
                                        output=FilePath,
                                        parseargs='shglob',
                                        idempotent=True,
                                        threaded=True,
                                        options=[['-l', '--long'],['-a', '--all']])

    def __ls_dir(self, dir, show_all):
        fs = Filesystem.getInstance()
        for x in DirectoryGenerator(dir):
            if show_all:
                yield x
            else:
                bn = os.path.basename(x)
                if not (fs.get_basename_is_ignored(bn)):
                    yield x

    def execute(self, context, args, options=[]):
        show_all = '-a' in options
        long_fmt = '-l' in options
            
        if len(args) in (0, 1):
            if len(args) == 1:
                arg0_path = FilePath(args[0], context.cwd)
                stbuf = os.stat(arg0_path)
            else:
                stbuf = None
                arg0_path = None
            if stbuf and stat.S_ISDIR(stbuf.st_mode):
                dir = arg0_path
            elif stbuf:
                yield arg0_path
                return
            else:
                dir = context.cwd
            generator = self.__ls_dir(dir, show_all)
        else:
            generator = xmap(lambda arg: FilePath(arg, context.cwd), args)
        generator = sorted(generator, locale.strcoll)
        for x in generator:
            yield x
BuiltinRegistry.getInstance().register(LsBuiltin())
