# -*- tab-width: 4 -*-
import sys,os,logging,platform

from hotwire.sysdep import is_windows, is_unix, is_linux

class BaseProcessManager(object):
    def get_extra_subproc_args(self):
        return {}

    def get_processes(self):
        raise NotImplementedError()

    def interrupt_pid(self, pid):
        raise NotImplementedError()

    def kill_pid(self, pid):
        raise NotImplementedError()
    
    def get_self(self):
        pid = os.getpid()
        for proc in self.get_processes():
            if proc.pid == pid:
                return proc
        return None    

class Process(object):
    def __init__(self, pid, cmd, owner_name):
        self.pid = pid
        self.cmd = cmd
        self.owner_name = owner_name

    def kill(self):
        raise NotImplementedError()

    def __str__(self):
        return "Process '%s' (%s) of %s" % (self.cmd, self.pid, self.owner_name)

_module = None
if is_linux():
    import hotwire.sysdep.proc_impl.proc_linux
    _module = hotwire.sysdep.proc_impl.proc_linux
elif is_unix():
    import hotwire.sysdep.proc_impl.proc_unix
    _module = hotwire.sysdep.proc_impl.proc_unix
elif is_windows():
    import hotwire.sysdep.proc_impl.proc_win32
    _module = hotwire.sysdep.proc_impl.proc_win32
else:
    raise NotImplementedError("No Process implemented for %s!" % (platform.system(),))

_instance = None
class ProcessManager(object):
    @staticmethod
    def getInstance():
        global _instance
        if _instance is None:
            if not _module:
                raise NotImplementedError("Couldn't find a process implementation")
            _instance = _module.getInstance()
        return _instance
