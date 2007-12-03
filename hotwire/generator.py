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

import gobject

class Generator(object):
    def __iter__(self):
        raise NotImplementedError()

class CompoundGenerator(Generator):
    def __init__(self, children=None):
        self.__children = children

    def _set_children(self, children):
        self.__children = children
        
    def get_children(self):
        return self.__children

    def __iter__(self):
        for child in self.__children:
            for result in child:
                yield result

class GeneratorPureFilter(Generator):
    def __init__(self, source, func):
        self.__source = source
        self.__filter_func = func

    def __iter__(self):
        for arg in self.__source: 
			if self.__filter_func(arg):
				yield arg	

class GeneratorFilter(Generator):
    def __init__(self, source, func):
        self.__source = source
        self.__filter_func = func

    def __iter__(self):
        for arg in self.__source: 
            (match, result) = self.__filter_func(arg)
            if match:
                yield result

class HeuristicOrderingGenerator(Generator):
    def __init__(self, generator, matches, init=30, factor=1.3):
        match_count = len(matches)
        unmatched = []
        remaining = generator
        step = 0
        while True:
            source = unmatched or remaining
            if not source:
                return
            offset = step*factor
            start = offset
            end = min(match_count, start+init)
            for j in xrange(start, end):
                match = matches[j]
                if item == match:
                    yield match
                    break
                    
