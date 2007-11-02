#from __future__ import with_statement

import threading, Queue, logging

import gobject

from singletonmixin import Singleton

_logger = logging.getLogger("hotwire.Async")

class MiniThreadPool(Singleton):
    """A Thread pool.  Seems like a missing battery from the Python standard library..."""
    def __init__(self):
        _logger.debug("Creating MiniThreadPool")
        self.__queue_cond = threading.Condition()
        self.__queue = []
        self.__avail_threads = 0
        self.__thread_count = 0
        self.__max_threads = 30

    def run(self, callable, args=()):
        self.__queue_cond.acquire()
        if not self.__avail_threads and self.__thread_count < self.__max_threads:
            thr = threading.Thread(target=self.__worker, name="MiniThreadPool Thread")
            _logger.debug("Created thread %s", thr)
            thr.setDaemon(True)
            thr.start()
            self.__thread_count += 1
        self.__queue.append((callable, args))    
        self.__queue_cond.notify()
        self.__queue_cond.release()
            
    def __worker(self):
        while True:
            _logger.debug("thread %s waiting", threading.currentThread())
            self.__queue_cond.acquire()
            self.__avail_threads += 1
            while not self.__queue:
                self.__queue_cond.wait()
            (cb, args) = self.__queue.pop(0)
            self.__avail_threads -= 1
            self.__queue_cond.release()
            try:
                _logger.debug("thread %s executing cb", threading.currentThread())
                cb(*args)
            except:
                logging.exception("Exception in thread pool worker")

class IterableQueue(Queue.Queue):
    def __init__(self):
        Queue.Queue.__init__(self)
        self.__lock = threading.Lock()
        self.__handler_idle_id = 0
        self.__handler = None
        self.__handler_args = None

    def connect(self, handler, *args):
        self.__lock.acquire()
        assert(self.__handler is None)
        self.__handler_args = args
        self.__handler = handler
        self.__lock.release()
        if not self.empty():
            self.__add_idle()

    def disconnect(self):
        self.__lock.acquire()
        self.__handler = None
        if self.__handler_idle_id > 0:
            gobject.source_remove(self.__handler_idle_id)
        self.__lock.release()

    def __do_idle(self):
        self.__lock.acquire()
        self.__handler_idle_id = 0
        handler = self.__handler
        self.__lock.release()
        if handler:
            return handler(self, *self.__handler_args)

    def __add_idle(self):
        self.__lock.acquire()
        if self.__handler_idle_id == 0 and self.__handler:
            self.__handler_idle_id = gobject.timeout_add(200, self.__do_idle, priority=gobject.PRIORITY_LOW)
        self.__lock.release()

    def put(self, *args):
        Queue.Queue.put(self, *args)
        self.__add_idle()
        
    def iter_avail(self):
        try:
            while True:
                val = self.get(False)
                if val is not None:
                    yield val
        except Queue.Empty, e:
            pass

    def __iter__(self):
        for obj in QueueIterator(self):
            yield obj

class QueueIterator(object):
    def __init__(self, source):
        self._source = source

    def __iter__(self):
        item = True
        while not (item is None):
            item = self._source.get()
            if not (item is None):
                yield item
            else:
                break
