# -*- tab-width: 4 -*-
import os, sys, subprocess, string, threading, logging
try:
    import pty, termios
    pty_available = True
except:
    pty_available = False

import hotwire
from hotwire.text import MarkupText
from hotwire.async import MiniThreadPool
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema
from hotwire.sysdep import is_windows, is_unix
from hotwire.sysdep.proc import ProcessManager

_logger = logging.getLogger("hotwire.builtin.Sh")

class ShBuiltin(Builtin):
    """Execute a system shell command, returning output as text."""
    def __init__(self):
        super(ShBuiltin, self).__init__('sh',
                                        input=InputStreamSchema(str, optional=True),
                                        output=OutputStreamSchema(str, opt_formats=['text/chunked']),
                                        parseargs=(is_windows() and 'shglob' or 'str-shquoted'),
                                        hasstatus=True,
                                        threaded=True)

    def __on_input(self, input, stdin):
        for val in input.iter_avail():
            stdin.write(str(val))
            stdin.write('\n')
        stdin.flush()
            
    def __inputwriter(self, input, stdin):
        for val in input:
            stdin.write(str(val))
            stdin.write('\n')
        stdin.flush()

    @staticmethod
    def __unbuffered_readlines(stream):
        try:
            line = stream.readline()
            while line:
                yield line
                line = stream.readline()
        except IOError, e:
            pass

    def cancel(self, context):
        if context.attribs.has_key('pid'):
            pid = context.attribs['pid']
            _logger.debug("cancelling pid %s", pid)
            ProcessManager.getInstance().interrupt_pid(pid)
            
    def cleanup(self, context):
        try:
            if 'input_connected' in context.attribs:
                _logger.debug("disconnecting from stdin")
                if context.input:                
                    context.input._source.disconnect()
        except:
            _logger.debug("failed to disconnect from stdin", exc_info=True)               
            pass

    def execute(self, context, arg, out_opt_format=None):
        # This function is complex.  There are two major variables.  First,
        # are we on Unix or Windows?  This is effectively determined by
        # pty_available, though I suppose some Unixes might not have ptys.
        # Second, out_opt_format tells us whether we want to stream the 
        # output as lines (out_opt_format is None), or as unbuffered byte chunks
        # (determined by text/chunked).
        
        if pty_available:
            # We create a pseudo-terminal to ensure that the subprocess is line-buffered.
            # Yes, this is gross, but as far as I know there is no other way to
            # control the buffering used by subprocesses.
            (master_fd, slave_fd) = pty.openpty()
            
            _logger.debug("allocated pty fds %d %d", master_fd, slave_fd)
            stdout_target = slave_fd
            stdin_target = subprocess.PIPE
        else:
            _logger.debug("no pty available, not allocating fds")
            (master_fd, slave_fd) = (None, None)
            stdout_target = subprocess.PIPE
            stdin_target = subprocess.PIPE

        subproc_args = {'bufsize': 0,
                        'stdin': context.input and stdin_target or None,
                        'stdout': stdout_target,
                        'stderr': subprocess.STDOUT,
                        'cwd': context.cwd}
        if is_windows():
            subproc_args['universal_newlines'] = True                
            subproc = subprocess.Popen(arg, **subproc_args)
        elif is_unix():
            ## On Unix, we re've requoted all the arguments, and now we process
            # them as a single string through /bin/sh.  This is a gross hack,
            # but necessary if we want to allow people to use shell features
            # such as for loops, I/O redirection, etc.  In the longer term
            # future, we want to implement replacements for both of these,
            # and execute the command directly.
            subproc_args['close_fds'] = True
            subproc_args['preexec_fn'] = os.setsid
            subproc = subprocess.Popen(['/bin/sh', '-c', arg], **subproc_args)
        else:
            assert(False)
        if not subproc.pid:
            if master_fd is not None:
                os.close(master_fd)
            if slave_fd is not None:
                os.close(slave_fd)
            raise ValueError('Failed to execute %s' % (arg,))
        context.attribs['pid'] = subproc.pid
        if context.cancelled:
            self.cancel(context)
        context.status_notify('pid %d' % (context.attribs['pid'],))
        if context.input:        
            stdin_stream = subproc.stdin
            # FIXME hack - need to rework input streaming                
            if context.input_is_first:
                context.attribs['input_connected'] = True
                context.input.connect(self.__on_input, stdin_stream)
            else:
                MiniThreadPool.getInstance().run(self.__inputwriter, args=(context.input, stdin_stream))
        if pty_available:
            os.close(slave_fd)
            stdout_fd = master_fd
            stdout_read = os.fdopen(master_fd, 'r')
        else:
            stdout_read = subproc.stdout
            stdout_fd = subproc.stdout.fileno
        if out_opt_format is None:
            for line in ShBuiltin.__unbuffered_readlines(stdout_read):
                yield line[:-1]
        elif out_opt_format == 'text/chunked':       
            try:
                buf = os.read(stdout_fd, 5)
                while buf:
                    print "yield: '%s'" % (buf,)
                    yield buf
                    buf = os.read(stdout_fd, 5)
            except OSError, e:
                pass
        else:
            assert(False)
        stdout_read.close()
        retcode = subproc.wait()
        if retcode >= 0:
            retcode_str = '%d' % (retcode,)
        else:
            retcode_str = 'signal %d' % (abs(retcode),)
        context.status_notify('Exit %s' % (retcode_str,))
        
BuiltinRegistry.getInstance().register(ShBuiltin())
