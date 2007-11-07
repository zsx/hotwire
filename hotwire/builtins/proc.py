import hotwire

from hotwire.sysdep.proc import ProcessManager, Process
from hotwire.builtin import Builtin, BuiltinRegistry

class PsBuiltin(Builtin):
    """List all processes."""
    def __init__(self):
        super(PsBuiltin, self).__init__('proc',
                                        output=Process,
                                        idempotent=True,
                                        options=[['-u', '--user'],],                                        
                                        threaded=True)

    def execute(self, context, options=[]):
        myself_only = '-u' in options        
        pm = ProcessManager.getInstance()
        if not myself_only:
            for proc in pm.get_processes():
                yield proc
        else:
            selfproc = pm.get_self()
            selfname = selfproc.owner_name            
            for proc in pm.get_processes():
                if proc.owner_name != selfname:
                    continue
                yield proc
BuiltinRegistry.getInstance().register(PsBuiltin())
