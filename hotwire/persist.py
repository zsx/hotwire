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

import os, re, sys, logging, pickle, tempfile, threading

import gobject

import hotwire
from hotwire.externals.singletonmixin import Singleton
from hotwire.async import MiniThreadPool
from hotwire.sysdep.fs import Filesystem
from hotwire.fs import atomic_rename

_logger = logging.getLogger("hotwire.Persist")

# TODO - make this a magic dynamic proxy
class Persistent(object):
    def __init__(self, name, obj):
        self._obj = obj
        self._name = name
        self.lock = threading.Lock()

    def get(self, lock=False):
        if lock:
            self.lock.acquire()
        return self._obj

    def save(self):
        """Queue this object for storage.  You must have invoked get with lock=True."""
        self.lock.release()
        Persister.getInstance()._persist(self)

    def unlock(self):
        self.lock.release()

class Persister(Singleton):
    """Stores named objects using Python pickling.  Objects are queued
    for storage asynchronously.  Reading is synchronous."""
    def __init__(self):
        super(Persister, self).__init__()
        self.__persistents = {}
        self.__queued_persists = set()
        self.__idle_persist_id = 0
        self.__persist_running = False
        self.__persist_condition = threading.Condition()
        self.__dir = Filesystem.getInstance().makedirs_p(os.path.join(Filesystem.getInstance().get_conf_dir(), 'persist'))
        self.__disabled = False

    def disable(self):
        _logger.info("Persistence disabled")
        self.__disabled = True

    def _persist(self, persistent):
        name = persistent._name
        if self.__disabled:
            return
        self.__queued_persists.add(persistent)
        if self.__idle_persist_id == 0:
            self.__idle_persist_id = gobject.timeout_add(6000, self.__idle_do_persist)

    def __obj_pathname(self, name):
        return os.path.join(self.__dir, name + '.p')

    def load(self, name, default=None):
        if not self.__persistents.has_key(name):
            self.__persistents[name] = Persistent(name, self._read(name) or default)
        return self.__persistents[name]

    def _read(self, name):
        """Load serialized object named by name, or None"""
        try:
            f = open(self.__obj_pathname(name), 'rb')
            obj = pickle.load(f)
            f.close()
        except IOError, e:
            return None
        return obj

    def flush(self):
        _logger.debug("doing persistence flush")
        # synchronize with any current writing
        self.__wait_not_running()
        self.__persist_condition.release()
        if self.__idle_persist_id > 0:
            gobject.source_remove(self.__idle_persist_id)
        self.__write_persists(self.__queued_persists)
        _logger.debug("persistence flush complete")

    def __wait_not_running(self):
        _logger.debug("waiting on running condition")
        self.__persist_condition.acquire()
        while self.__persist_running:
            self.__persist_condition.wait()

    def __idle_do_persist(self):
        _logger.debug("idle snapshotting %d objects for write", len(self.__queued_persists))
        persists = self.__queued_persists
        self.__queued_persists = set()
        MiniThreadPool.getInstance().run(self.__write_persists, args=(persists,))
        self.__idle_persist_id = 0

    def __write_persists(self, snapshot):
        _logger.debug("entering write_persists (%d objects)", len(snapshot))
        self.__wait_not_running()
        self.__persist_running = True
        self.__persist_condition.release()
        for obj in snapshot:
            name = obj._name
            val = obj.get(lock=True)
            target_name = self.__obj_pathname(name)
            _logger.debug("saving %s to %s", name, target_name)
            (tempfd, temp_name) = tempfile.mkstemp('', target_name, self.__dir)
            tempf = os.fdopen(tempfd, 'wb')
            pickle.dump(val, tempf)
            tempf.close()
            # FIXME Windows portability need atomic rename
            atomic_rename(temp_name, target_name)
            obj.unlock()
        self.__persist_condition.acquire()
        self.__persist_running = False 
        self.__persist_condition.notifyAll()
        self.__persist_condition.release()
        _logger.debug("write_persists complete")
        
