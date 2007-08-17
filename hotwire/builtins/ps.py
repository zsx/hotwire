import hotwire

from hotwire.sysdep.proc import ProcessManager, Process
from hotwire.builtin import Builtin, BuiltinRegistry, OutputStreamSchema, idempotent

class PsBuiltin(Builtin):
    """List all processes."""
    def __init__(self):
        super(PsBuiltin, self).__init__('ps',
                                        output=OutputStreamSchema(Process))

    @idempotent()
    def execute(self, context):
        for proc in ProcessManager.getInstance().get_processes():
            yield proc
BuiltinRegistry.getInstance().register(PsBuiltin())
