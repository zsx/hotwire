# -*- tab-width: 4 -*-
import os,sys,logging,string

from hotwire.sysdep.proc import Process
from hotwire.sysdep.win32 import win_exec_re, win_dll_re

import win32process,win32api,win32security,win32con,ntsecuritycon

_logger = logging.getLogger('hotwire.proc.Win32')

class WindowsProcess(Process):
    def __init__(self, pid):
        ph = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION|win32con.PROCESS_VM_READ,0,pid)
        token = win32security.OpenProcessToken(ph, win32con.TOKEN_QUERY)
        sid,attr = win32security.GetTokenInformation(token, ntsecuritycon.TokenUser)
        (username, proc_domain, proc_type) = win32security.LookupAccountSid(None, sid)
        exes = []
        modules = []
        for module in win32process.EnumProcessModules(ph):
            fn = win32process.GetModuleFileNameEx(ph, module)
            if win_exec_re.search(fn):
                exes.append(fn)        
            else:
                modules.append(fn)
        # gross but...eh
        if not exes:
            nondll = []
            for mod in modules:
                if not win_dll_re.search(mod):
                    nondll.append(mod)
            if nondll:
                exes.append(nondll[0])
        super(WindowsProcess, self).__init__(pid, string.join(exes, ' '), username)

class Win32ProcessManager(object):
    def get_processes(self):
        for pid in win32process.EnumProcesses():
            if pid > 0:
                try:
                    yield WindowsProcess(pid) 
                except:
                    #_logger.exception("Couldn't get process information for pid %d", pid)
                    continue

    def interrupt_pid(self, pid):
        self.kill_pid(pid)

    def kill_pid(self, pid):
        ph = win32api.OpenProcess(win32con.PROCESS_TERMINATE|win32con.PROCESS_QUERY_INFORMATION,0,pid)
        win32api.TerminateProcess(ph, 0)

def getInstance():
    return Win32ProcessManager()
