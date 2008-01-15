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
import symbol,parser,code,threading

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema

from hotwire.fs import path_join
from hotwire.sysdep.fs import Filesystem
from hotwire.externals.rewrite import rewrite_and_compile

class PyEvalBuiltin(Builtin):
    __doc__ = _("""Compile and execute Python expression.
Iterable return values (define __iter__) are expanded.  Other values are
expressed as an iterable which yielded a single object.""")
 
    def __init__(self):
        super(PyEvalBuiltin, self).__init__('py-eval',
                                            threaded=True,
                                            output=OutputStreamSchema('any'),
                                            options=[['-f', '--file']])

    def __itervalue(self, o):
        if isinstance(o, dict):
            for v in o.iteritems():
                yield v
        elif hasattr(o, '__iter__'):
            for v in o:
                yield v
        else:
            yield o         

    def execute(self, context, args, options=[]):
        if len(args) > 1:
            raise ValueError(_("Too many arguments specified"))
        if len(args) < 1:
            raise ValueError(_("Too few arguments specified"))
        locals = {'hot_context': context,
                  'hot_selected': context.selected_output,
                  'hot_current': context.current_output}
        last_value = None
        if '-f' in options:
            fpath = path_join(context.cwd, args[0])
            f = open(fpath)
            compiled = compile(f.read(), fpath, 'exec')
            f.close()
            exec compiled in locals
            try:
                mainfunc = locals['main']
            except KeyError, e:
                yield None
                return
            if not hasattr(mainfunc, '__call__'):
                yield None
                return
            retv = mainfunc()
            for v in self.__itervalue(retv):
                yield v
        else:
        # We want to actually get the object that results from a user typing
        # input such as "20" or "import os; os".  The CPython interpreter
        # has some deep hackery inside which transforms "single" input styles
        # into "print <input>".  That's not suitable for us, because we don't
        # want to spew objects onto stdout; we want to actually get the object
        # itself.  Thus we use some code from Reinteract to rewrite the 
        # Python AST to call custom functions.
        # Yes, it's lame.
            def handle_output(myself, *args):
                myself['result'] = args[-1]
            locals['_hotwire_handle_output'] = handle_output
            locals['_hotwire_handle_output_self'] = {'result': None}
            (compiled, mutated) = rewrite_and_compile(args[0], output_func_name='_hotwire_handle_output', output_func_self='_hotwire_handle_output_self')
            exec compiled in locals
            for v in self.__itervalue(locals['_hotwire_handle_output_self']['result']):
                yield v

BuiltinRegistry.getInstance().register(PyEvalBuiltin())
