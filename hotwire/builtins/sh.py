# -*- tab-width: 4 -*-
import subprocess, string, threading, logging

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
                                        outputs=[OutputStreamSchema(str),
                                                 OutputStreamSchema(str, name='stderr',
                                                                    merge_default=True)])

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

    def __stderrwriter(self, context, stderr):
        for val in ShBuiltin.__unbuffered_readlines(stderr):
            nonewline_val = val[:-1] 
            markup = MarkupText(nonewline_val)
            markup.add_markup('red', 0, len(nonewline_val))
            context.auxstream_append('stderr', markup)
        stderr.close()

    def cancel(self, context):
        if context.attribs.has_key('pid'):
            ProcessManager.getInstance().interrupt_pid(context.attribs['pid'])

    @parseargs('str-shquoted')
    @hasstatus()
    def execute(self, context, arg):
        extra_args = ProcessManager.getInstance().get_extra_subproc_args()
        
        subproc = subprocess.Popen([arg],
                                   shell=True,
                                   bufsize=1,
                                   universal_newlines=True,
                                   stdin=context.input and subprocess.PIPE or None,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=context.cwd,
								   **extra_args) 
        if not subproc.pid:
			raise ValueError('Failed to execute %s' % (arg,))
        context.attribs['pid'] = subproc.pid
        if context.cancelled:
            self.cancel(context)
        context.status_notify('Running (pid %d)' % (context.attribs['pid'],))
        if context.input:
            MiniThreadPool.getInstance().run(lambda: self.__inputreader(context.input, subproc.stdin))
        MiniThreadPool.getInstance().run(lambda: self.__stderrwriter(context, subproc.stderr))
        for line in ShBuiltin.__unbuffered_readlines(subproc.stdout):
		    yield line[:-1]
        subproc.stdout.close()
        retcode = subproc.wait()
        if retcode >= 0:
            retcode_str = '%d' % (retcode,)
        else:
            retcode_str = 'signal %d' % (abs(retcode),)
        context.status_notify('Exit %s' % (retcode_str,))
        
BuiltinRegistry.getInstance().register(ShBuiltin())
