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

import os, sys, logging, inspect

import hotwire.fs
from hotwire.fs import path_normalize

_logger = logging.getLogger("hotwire.Script")

(PIPE, REDIR_IN, REDIR_OUT, REDIR_OUT_APPEND) = xrange(4)
 
def script(*args, **kwargs):
    from hotwire.command import Pipeline,HotwireContext
    if not 'context' in kwargs:
        kwargs['context'] = HotwireContext(initcwd=(kwargs.get('cwd', None)))
    return Pipeline.create(kwargs['context'], kwargs.get('resolver', None), *args)

from hotwire.builtin import Builtin
class PyFuncBuiltin(Builtin):
    def __init__(self, func, **kwargs):
        name = func.func_name
        if not name:
            raise ValueError("Couldn't determine name of function: %s" % (f,))
        self.__func = func
        self.__func_args = inspect.getargspec(func)
        # 0x20 appears to signify the function is a generator according to the CPython sources
        self.__func_is_generator = func.func_code.co_flags & 0x20
        if not self.__func_is_generator:
            kwargs['singlevalue'] = True
        kwargs['output'] = 'any'
        def execute(context, args, **kwargs):
            if len(self.__func_args[0]) == 0:
                result = self.__func()
            else:
                result = self.__func(context, args, **kwargs)                
            return result
        if self.__func_is_generator:
            def generator_execute(context, args, **kwargs):              
                for value in execute(context, args, **kwargs):
                    yield value
            self.execute = generator_execute
        else:
            self.execute = execute
        super(PyFuncBuiltin, self).__init__(name, **kwargs)
    
def _builtin(registerfunc, **kwargs):
    def builtin_wrapper(f):
        builtin = PyFuncBuiltin(f, **kwargs)
        registerfunc(builtin)
        return f
    return builtin_wrapper

def builtin_user(**kwargs):
    from hotwire.builtin import BuiltinRegistry    
    return _builtin(BuiltinRegistry.getInstance().register_user, **kwargs)
