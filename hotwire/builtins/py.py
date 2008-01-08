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

import os,sys,re,subprocess,sha,tempfile

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema

from hotwire.fs import path_join
from hotwire.sysdep.fs import Filesystem

class PyBuiltin(Builtin):
    __doc__ = _("""Process objects using Python code.""")
 
    PYCMD_NOINPUT_CONTENT = '''## Python Command
import os,sys,re
import gtk, gobject

# No input given
def execute(context, input):
  yield''' 
    
    PYCMD_WITHINPUT_CONTENT = '''## Python Command
import os,sys,re
import gtk, gobject

# Input type: %r
def execute(context, input):
  for obj in input:
    yield ''' 
    def __init__(self):
        super(PyBuiltin, self).__init__('py',
                                        threaded=True,
                                        input=InputStreamSchema('any', optional=True),
                                        output=OutputStreamSchema('any'))

    def execute(self, context, args):
        fs = Filesystem.getInstance()
        scriptdir = fs.make_conf_subdir('scripts')
        (fd, fpath) = tempfile.mkstemp('.py', 'script', scriptdir)
        shasum = sha.new()
        if context.input_type is not None:
            content = self.PYCMD_WITHINPUT_CONTENT % (context.input_type,)
        else:
            content = self.PYCMD_NOINPUT_CONTENT
        f = os.fdopen(fd, 'w')
        shasum.update(content)
        f.write(content)
        f.close()
        sum_hex = shasum.hexdigest()
        subprocess.check_call([os.environ['EDITOR'], fpath], cwd=context.cwd, close_fds=True)
        buf = open(fpath).read()
        new_sum = sha.new()        
        new_sum.update(buf)
        new_sum_hex = new_sum.hexdigest() 
        if new_sum_hex == sum_hex:
            os.unlink(fpath)
            raise ValueError(_("Script not modified, aborting"))
        new_fpath = os.path.join(scriptdir, new_sum_hex+'.py')
        os.rename(fpath, new_fpath)
        code = compile(buf, '<input>', 'exec')
        locals = {}
        exec code in locals
        execute = locals['execute']
        custom_out = execute(context, context.input)
        if custom_out is None:
            return
        if hasattr(custom_out, '__iter__'):
            for o in custom_out:
                yield o
        else:
            yield custom_out

BuiltinRegistry.getInstance().register(PyBuiltin())
