# -*- tab-width: 4 -*-
import os, sys, subprocess, string, threading, logging
try:
    import pty
    pty_available = True
except:
    pty_available = False

import hotwire
from hotwire.text import MarkupText
from hotwire.async import MiniThreadPool
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema, parseargs, hasstatus
from hotwire.sysdep.proc import ProcessManager

_logger = logging.getLogger("hotwire.builtin.Sh")

class ShBuiltin(Builtin):
    """Execute a system shell command, returning output as text."""
    def __init__(self):
        super(ShBuiltin, self).__init__('sh',
                                        input=InputStreamSchema(str, optional=True),
                                        outputs=[OutputStreamSchema(str)])

    def __inputreader(self, input, stdin):
        for val in input:
            stdin.write(str(val))
            stdin.write('\n')
        stdin.close()

    @staticmethod
    def __unbuffered_readlines(stream):
        try:
            line = stream.readline()
            while line:
                yield line
                line = stream.readline()
        except IOError, e:
            _logger.debug("Caught error reading from subprocess pipe", exc_info=True)
            pass

    def cancel(self, context):
        if context.attribs.has_key('pid'):
            ProcessManager.getInstance().interrupt_pid(context.attribs['pid'])
            
    def cleanup(self, context):
        if 'master_fd' in context.attribs:
            os.close(context.attribs['master_fd'])
        if 'stdout_read' in context.attribs:
            context.attribs['stdout_read'].close()

    @parseargs('str-shquoted')
    @hasstatus()
    def execute(self, context, arg):
        extra_args = ProcessManager.getInstance().get_extra_subproc_args()

        if pty_available:
            # We create a pseudo-terminal to ensure that the subprocess is line-buffered.
            # Yes, this is gross, but as far as I know there is no other way to
            # control the buffering used by subprocesses.
            (master_fd, slave_fd) = pty.openpty()
            context.attribs['master_fd'] = master_fd
            _logger.debug("allocated pty fds %d %d", master_fd, slave_fd)
            stdout_target = slave_fd
        else:
            _logger.debug("no pty available, not allocating fds")
            (master_fd, slave_fd) = (None, None)
            stdout_target = subprocess.PIPE

        subproc = subprocess.Popen([arg],
                                   shell=True,
                                   bufsize=1,
                                   universal_newlines=True,
                                   stdin=context.input and subprocess.PIPE or None,
                                   stdout=stdout_target,
                                   stderr=subprocess.STDOUT,
                                   cwd=context.cwd,
                                   **extra_args)
        if not subproc.pid:
            os.close(slave_fd)
            raise ValueError('Failed to execute %s' % (arg,))
        context.attribs['pid'] = subproc.pid
        if context.cancelled:
            self.cancel(context)
        context.status_notify('pid %d' % (context.attribs['pid'],))
        if context.input:
            MiniThreadPool.getInstance().run(lambda: self.__inputreader(context.input, subproc.stdin))
        if pty_available:
            os.close(slave_fd)
            stdout_read = os.fdopen(master_fd, 'rU')
            del context.attribs['master_fd']
            context.attribs['stdout_read'] = stdout_read
        else:
            stdout_read = subproc.stdout
        for line in ShBuiltin.__unbuffered_readlines(stdout_read):
            yield line[:-1]
        stdout_read.close()
        retcode = subproc.wait()
        if retcode >= 0:
            retcode_str = '%d' % (retcode,)
        else:
            retcode_str = 'signal %d' % (abs(retcode),)
        context.status_notify('Exit %s' % (retcode_str,))
        
BuiltinRegistry.getInstance().register(ShBuiltin())
