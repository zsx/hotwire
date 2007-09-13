# -*- tab-width: 4 -*-
import os,sys,re,string, pwd

from hotwire.sysdep.proc_impl.proc_unix import UnixProcessManager, UnixProcess

class LinuxProcess(UnixProcess):
    uid_re = re.compile(r'^Uid:\s+(\d+)')
    def __init__(self, pid):
        bincmd = file(os.path.join('/proc', str(pid), 'cmdline'), 'rb').read()
        self.arguments = bincmd.split('\x00') 
        owner_uid = -1
        for line in file(os.path.join('/proc', str(pid), 'status')):
            match = self.uid_re.search(line)
            if match:
                owner_uid = int(match.group(1))
        super(LinuxProcess, self).__init__(pid, string.join(self.arguments, ' '), pwd.getpwuid(owner_uid)[0])

class LinuxProcessManager(UnixProcessManager):
    def get_processes(self):
        num_re = re.compile(r'\d+')
        for d in os.listdir('/proc'):
            if num_re.match(d):
                try:
                    yield LinuxProcess(int(d))
                except OSError, e:
                    # Ignore processes that go away as we read them
                    pass
                except IOError, e:
                    pass
                
def getInstance():
    return LinuxProcessManager()
