import os, sys, xmlrpclib, logging, StringIO, threading, Queue
from UserDict import IterableUserDict

import gobject, paramiko

from hotwire import FilePath
from hotwire.async import QueueIterator, CancellableQueueIterator, MiniThreadPool
from hotwire.singletonmixin import Singleton
import hotwire.util

_logger = logging.getLogger('hotwire.Minion')

thread_debug = False
minion_debug = False

class MinionEvent(object):
    def __init__(self, chanid, name, *args):
        self.chanid = chanid
        self.name = name
        self.args = args

    def __str__(self):
        return "MinionEvent '%s': %s" % (self.name, self.args)

class RemoteObject(object):
    def __init__(self, cls, strval):
        self.cls = cls
        self.strval = strval

class RemoteFilePath(str):
    pass

class RemoteObjectFactory(Singleton):
    def __init__(self):
        self.__objmap = {}

    def register(cls, constructor):
        self.__objmap[cls.__name__] = constructor
        
    def load(clsname, strval, *args):
        if self.__objmap.has_key(clsname):
            return self.__objmap[clsname](*args)
        return RemoteObject(clsname, strval)

class MinionChannel(object):
    def __init__(self, id, write_func):
        super(MinionChannel, self).__init__()
        self.id = id
        self.event_queue = Queue.Queue()
        self.__write_func = write_func

    def invoke(self, methname, *args):
        _logger.debug("Invoking %s %s", methname, args)
        # keep in sync with initcode
        req = xmlrpclib.dumps(tuple([self.id] + list(args)), methname)
        self.__write_func('%d\n' % (len(req),), req)

class MinionDownloadState(object):
    def __init__(self, fname, status_msg=None, bytes_read=None, bytes_total=None):
        self.fname = fname
        self.status_msg = status_msg
        self.bytes_read = bytes_read
        self.bytes_total = bytes_total

class Minion(gobject.GObject):
    __gsignals__ = {
        "download" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,
                                                                   gobject.TYPE_PYOBJECT,
                                                                   gobject.TYPE_PYOBJECT,
                                                                   gobject.TYPE_PYOBJECT)),
        "exception" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        "status" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        "terminal" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,gobject.TYPE_STRING)),
        "cwd" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        "stderr" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        super(Minion, self).__init__()
        self.__stdin_lock = threading.Lock()
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.errbuf = StringIO.StringIO('')
        self.__channel_serial = 0
        self.__channels = {}
        self.__idle_process_events_id = 0
        self.__initialized = False
# WARNING: Do not use ' in here for current implementation reasons
# also anything using \ will need to be double-backslashed
        self.initcode = """
import sys,os
sys.stderr.write("at your service\\n")
sys.path.append(os.path.join(os.path.expanduser("~"), ".hotwire"))
import hotwire.minion_impl
hotwire.minion_impl.main()
"""

    def __channel_write(self, *args):
        # TODO - convert to event queue?  Possible deadlock?
        self.__stdin_lock.acquire()
        for arg in args:
            self.stdin.write(arg)
        self.stdin.flush()
        self.__stdin_lock.release()

    def set_lcwd(self, lcwd):
        self._lcwd = lcwd

    def open_channel(self):
        self.__channel_serial = serial = self.__channel_serial + 1
        self.__channels[serial] = channel = MinionChannel(serial, self.__channel_write)
        return channel

    def _set_minion_streams(self, stdin, stdout, stderr):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        MiniThreadPool.getInstance().run(self.__event_thread_main)

    def __event_thread_main(self):
        while True:
            reqmeta = self.stdout.readline()
            if reqmeta == '':
                raise Exception('EOF from minion')
            reqmeta = reqmeta.strip()            
            try:
                reqlen = int(reqmeta)
            except ValueError, e:
                raise Exception("Failed to parse reqlen '%s'"  % (reqmeta,))
            _logger.debug("reading event (%d bytes)", reqlen)
            request = self.stdout.read(reqlen)
            if len(request) != reqlen:
                _logger.info("unexpected EOF in stream")
                break
            (params, ignored) = xmlrpclib.loads(request)
            event = (MinionEvent(params[0], params[1], *(params[2])))
            _logger.debug("read event: %s", event)
            if event.chanid == -1:
                if event.name == 'Cwd':
                    gobject.idle_add(lambda e: self.emit("cwd", e.args[0]), event)
                elif event.name == 'StartDownload':
                    gobject.idle_add(lambda e: self.start_download(e.args[0]), event)
                elif event.name == 'ExecTerminal':
                    gobject.idle_add(lambda e: self.exec_terminal(*e.args), event)
                else:
                    _logger.warn("Unhandled core event %s", event)
            else:
                channel = self.__channels[event.chanid]
                channel.event_queue.put(event)
            
    def close(self):
        raise NotImplementedError()

class SshMinion(Minion):
    def __init__(self, host):
        super(SshMinion,self).__init__()
        self.host = host
        self.__client = paramiko.SSHClient()
        self.__client.load_system_host_keys()
        _logger.debug('Creating SSH minion for %s', host)
        self.emit("status", "Connecting to %s" % (host,))
        self.__client.connect(host)
        cmd = "python -c \'%s\'%s%s" % (self.initcode,
                                        minion_debug and " --debug" or "",
                                        thread_debug and " --thread-debug" or "")
        self.emit("status", "Setting up...")
        (stdin, stdout, stderr) = self.__client.exec_command(cmd)
        _logger.debug('Minion initiated')
        self._set_minion_streams(stdin, stdout, stderr)
        self._sftp = None
        self.emit("status", "Connected")

        def write_stderr():
            for line in stderr:
                _logger.debug('Minion stderr: %s' % (line[0:-1],))
        MiniThreadPool.getInstance().run(write_stderr)

    def start_download(self, fname):
        if not self._sftp:
            self._sftp = self.__client.open_sftp()
        self.__emit_download_state(fname, 0, None)
        MiniThreadPool.getInstance().run(lambda: self.__do_download(self._lcwd, fname))
            
    def __do_download(self, lcwd, fname):
        bytes_read = 0
        bytes_total = None
        try:
            _logger.debug("using lcwd %s, fname %s", lcwd, fname)
            newf = os.path.join(lcwd, os.path.basename(fname))
            if os.access(newf, os.R_OK):
                trashf = os.path.join(hotwire.get_platform().get_trash_dir(),
                                      os.path.basename(newf))
                os.rename(newf, trashf)
            stats = self._sftp.lstat(fname)
            bytes_total = stats.st_size
            _logger.debug('stat of %s: %s', fname, bytes_total)
            # notify at most 100 times
            notify_readsize = max(bytes_total / 100, 512)
            notify_count = 0 
            self.__emit_download_state(fname, bytes_read, bytes_total)
            f = self._sftp.open(fname)
            newf = open(newf, 'wb')
            while True:
                buf = f.read(8192)
                if buf == '':
                    break
                newf.write(buf)
                bytes_read += len(buf)
                current_notify = (bytes_read / notify_readsize) 
                if current_notify >= notify_count:
                    self.__emit_download_state(fname, bytes_read, bytes_total)
                    notify_count = current_notify
            f.close()
            newf.close()
            self.__emit_download_state(fname, bytes_read, bytes_total)
        except Exception, e:
            _logger.exception("Caught exception in download: %s", e)
            self.__emit_download_state(fname, bytes_read, bytes_total, str(e))

    def __emit_download_state(self, fname, bytes_read, bytes_total, err=None):
        _logger.debug('emitting download state: %s %s %s %s',
                      fname, bytes_read, bytes_total, err)
        self.emit("download", fname, bytes_read, bytes_total, err)

    def exec_terminal(self, cmd, cwd):
        chan = self.__client._transport.open_session()
        chan.get_pty('vt100', 80, 24)
        chan.exec_command("cd %s; /bin/sh -c %s" % (hotwire.util.quote_shell_arg(cwd),
                                                    hotwire.util.quote_shell_arg(cmd)))
        hotwire.get_platform().open_terminal_window(chan, cmd)

    def close(self):
        self.__client.close()

    def __str__(self):
        return "ssh %s" % (self.host,)
        
if __name__ == '__main__':
    from logutil import init as loginit
    loginit('DEBUG', ['Minion'], 'hotwire.')
    sshmin = SshMinion('localhost')
    def write_stderr():
        for line in sshmin.stderr:
            sys.stderr.write('Minion stderr: %s' % (line,))
    MiniThreadPool.getInstance().run(write_stderr)
    channel = sshmin.open_channel()
    def write_events():
        for event in QueueIterator(channel.event_queue):
            print event
    MiniThreadPool.getInstance().run(write_events)

    gobject.threads_init()

    loop = gobject.MainLoop()
    
    def do_readinput(src, cond):
        if ((cond & gobject.IO_ERR) or (cond & gobject.IO_HUP)):
            loop.quit()
            return False
        pipeline = sys.stdin.readline().strip()
        if not pipeline:
            loop.quit()
            return False
        channel.invoke('create_pipeline', pipeline)
        sys.stdout.write("Pipeline: ")
        sys.stdout.flush()
        return True

    sys.stdout.write("Pipeline: ")
    sys.stdout.flush()
    gobject.io_add_watch(sys.stdin, gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP,
                         do_readinput)
    loop.run()
