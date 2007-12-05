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

import os, sys, stat

from hotwire.builtin import Builtin, BuiltinRegistry
from hotwire.fs import FilePath, DirectoryGenerator
from hotwire.completion import CdCompleter 

class CdBuiltin(Builtin):
    __doc__ = _("""Change working directory and list its contents.""")
    def __init__(self):
        super(CdBuiltin, self).__init__('cd',
                                        output=FilePath,
                                        parseargs='str',
                                        idempotent=True,
                                        threaded=True)

    def get_completer(self, context, args, i):
        return CdCompleter.getInstance()

    def execute(self, context, dir=None):
        if not dir:
            target_dir = os.path.expanduser("~")
        else:
            target_dir = dir
        new_dir = context.hotwire.chdir(target_dir)
        for result in BuiltinRegistry.getInstance()['ls'].execute(context, [new_dir]):
            yield result
BuiltinRegistry.getInstance().register(CdBuiltin())
