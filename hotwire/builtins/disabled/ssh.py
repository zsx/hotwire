from hotwire.builtin import Builtin, BuiltinRegistry, streamtypes

class SshBuiltin(Builtin):
    def __init__(self):
        super(SshBuiltin, self).__init__('ssh', nostatus=True)

    @streamtypes(None, None)
    def execute(self, context, host):
        context.hotwire.ssh(host)
        return []
BuiltinRegistry.getInstance().register(SshBuiltin())
