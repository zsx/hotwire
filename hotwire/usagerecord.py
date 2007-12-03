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

import os,sys,time,heapq

class Usage(object):
    def __init__(self, freq=1, usetime=None):
        self.freq = freq
        if usetime:
            self.usetime = usetime
        else:
            self.usetime = time.time()

    def __cmp__(self, other):
        return cmp(self.freq, other.freq)

    def __str__(self):
        return "Usage %s %s" % (self.freq, self.usetime)

class FrequentItem(object):
    def __init__(self, value, usage):
        self.value = value
        self.usage = usage

    def __cmp__(self, other):
        return cmp(self.usage, other.usage)

    def __str__(self):
        return "Frequent %s => %s" % (self.value, self.usage)

class UsageRecord(object):
    def __init__(self):
        self.__items = {}
        self.__frequentset = []
        self.__frequentset_size = 20

    def record(self, item):
        if self.__items.has_key(item):
            usage = self.__items[item]
            usage.freq += 1
            usage.usetime = time.time()
        else:
            usage = Usage() 
            self.__items[item] = usage
        val_is_frequent = False
        for val in self.__frequentset:
            if val.value == item:
                val_is_frequent = True
                break
        if not val_is_frequent:
            if (len(self.__frequentset) < self.__frequentset_size):
                heapq.heappush(self.__frequentset, FrequentItem(item, usage))
            elif usage > self.__frequentset[0].usage:
                heapq.heapreplace(self.__frequentset, FrequentItem(item, usage))

    def frequent(self):
        for item in self.__frequentset:
            yield item

    def __iter__(self):
        for item in self.__items.iteritems():
            yield item
            
            
        
