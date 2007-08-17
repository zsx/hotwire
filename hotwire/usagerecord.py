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
            
            
        
