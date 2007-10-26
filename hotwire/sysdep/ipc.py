# -*- tab-width: 4 -*-
import os,sys,platform,logging

import hotwire
from hotwire.sysdep import is_windows, is_unix

_logger = logging.getLogger("hotwire.sysdep.Ipc")

class BaseIpc(object):
    def singleton(self):
        raise NotImplementedError()

    def register_window(self, win):
        raise NotImplementedError()

    def raise_existing(self):
        raise NotImplementedError()

_module = None
if is_unix():
    import hotwire.sysdep.ipc_impl.ipc_dbus
    _module = hotwire.sysdep.ipc_impl.ipc_dbus
else:
    raise NotImplementedError("No Ipc implemented for %s!" % (platform.system(),))

_instance = None
class Ipc(object):
    @staticmethod
    def getInstance():
        global _instance
        if _instance is None:
            _instance = _module.getInstance()
        return _instance
