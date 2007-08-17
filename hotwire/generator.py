# -*- tab-width: 4 -*-

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
                    
