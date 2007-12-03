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

import os,sys

from hotwire.completion import BaseCompleter, Completion
from hotwire.builtins.sh import ShellCompleters
from hotwire.singletonmixin import Singleton

class RpmDbCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(RpmDbCompleter, self).__init__()
        self.__db = ['foo', 'bar-devel', 'crack-attack']
    def search(self, text, **kwargs):
        for pkg in self.__db:
            if pkg.startswith(text):
                yield Completion(pkg, 0, len(text), default_icon='gtk-floppy')
def rpm_completion(context, args, i):
    lastarg = args[i].text
    if lastarg.startswith('-q'):
        return RpmDbCompleter.getInstance()
ShellCompleters.getInstance()['rpm'] = rpm_completion 