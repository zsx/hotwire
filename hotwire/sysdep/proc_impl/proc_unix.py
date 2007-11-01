# -*- tab-width: 4 -*-
import os,signal,logging

from hotwire.sysdep.proc import Process

_logger = logging.getLogger("hotwire.proc.Unix")

class UnixProcess(Process):
    def kill(self):
        UnixProcessManager._kill_pid(self.pid)

class UnixProcessManager(object):
    
    @staticmethod
    def signal_pid_recurse(pid, signum):
        """This function should be used with caution."""
        try:
            pgid = os.getpgid(pid)
            try:
                os.killpg(pgid, signum)
                return # This hopefully worked, just return
            except OSError, e:
                _logger.warn("failed to send sig %s to process group %d", signum, pgid, exc_info=True)
        except OSError, e:
            _logger.warn("failed to get process group for %d", pid, exc_info=True)
            pgid = None
        # Ok, we failed to kill the process group; fall back to the pid itself
        try:
            os.kill(pid, signum)
            return True
        except OSError, e:
            _logger.debug("Failed to send sig %s to pid %d", signum, pid)
            return False    
    
    def interrupt_pid(self, pid):
        UnixProcessManager.signal_pid_recurse(pid, signal.SIGINT)

    def kill_pid(self, pid):
        UnixProcessManager._kill_pid(pid)

    @staticmethod
    def _kill_pid(pid):
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except OSError, e:
            _logger.debug("Failed to kill pid '%d': %s", pid, e)
            return False

def getInstance():
    return UnixProcessManager()