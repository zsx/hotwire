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

class PyEvalBuiltin(Builtin):
    __doc__ = _("""Compile and execute Python expression.
Iterable return values (define __iter__) are expanded.  Other values are
expressed as an iterable which yielded a single object.""")
 
    PYEVAL_CONTENT = '''
import os,sys,re
def execute(context, input):
  return %s''' 
    def __init__(self):
        super(PyEvalBuiltin, self).__init__('py-eval',
                                            threaded=True,
                                            output=OutputStreamSchema('any'))

    def execute(self, context, args, options=[]):
        if len(args) > 1:
            raise ValueError(_("Too many arguments specified"))
        if len(args) < 1:
            raise ValueError(_("Too few arguments specified"))
        buf = self.PYEVAL_CONTENT % (args[0],)
        code = compile(buf, '<input>', 'exec')
        locals = {}
        exec code in locals
        execute = locals['execute']
        custom_out = execute(context, context.input)
        if hasattr(custom_out, '__iter__'):
            for v in custom_out:
                yield v
        else:
            yield custom_out

BuiltinRegistry.getInstance().register(PyEvalBuiltin())
