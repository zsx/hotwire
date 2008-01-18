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

from hotwire.builtin import Builtin, BuiltinRegistry
from hotwire.fs import FilePath
from hotwire.sysdep.fs import Filesystem

class EditBuiltin(Builtin):
    __doc__ = _("""Launch the text editor.""")
    
    _ws_re = re.compile(r'\s+')
    
    def __init__(self):
        super(EditBuiltin, self).__init__('edit',
                                          aliases=['ed'],
                                          nostatus=True,
                                          idempotent=True)
 
    def execute(self, context, args):
        fs = Filesystem.getInstance()
        editor = os.environ['EDITOR']
        # TODO - try to detect current shell and parse using it
        editor_args = self._ws_re.split(editor)
        subproc_args = {'cwd': context.cwd}
        if context.gtk_event_time:
            env = dict(os.environ)
            env['DESKTOP_STARTUP_ID'] = 'hotwire%d_TIME%d' % (os.getpid(), context.gtk_event_time,)
            subproc_args['env'] = env
        editor_args.extend(args)
        subprocess.Popen(editor_args, **subproc_args)
        return []
BuiltinRegistry.getInstance().register(EditBuiltin())
