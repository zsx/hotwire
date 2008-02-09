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

import os,sys,re,os.path, stat,subprocess

from hotwire.builtin import Builtin, BuiltinRegistry, MultiArgSpec
from hotwire.fs import FilePath
from hotwire.sysdep.fs import Filesystem

class EditBuiltin(Builtin):
    __doc__ = _("""Launch the text editor.""")
    
    _ws_re = re.compile(r'\s+')
    
    def __init__(self):
        super(EditBuiltin, self).__init__('edit',
                                          aliases=['ed'],
                                          argspec=MultiArgSpec('paths', min=1),
                                          nodisplay=True,
                                          idempotent=True)
 
    def execute(self, context, args):
        from hotwire_ui.adaptors.editors import EditorRegistry
        prefeditor = EditorRegistry.getInstance().get_preferred()
        prefeditor.run_many(context.cwd, *args)
        return []
BuiltinRegistry.getInstance().register_hotwire(EditBuiltin())
