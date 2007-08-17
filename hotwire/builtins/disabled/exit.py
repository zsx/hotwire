from hotwire.builtin import Builtin, BuiltinRegistry, streamtypes, locality

class ExitBuiltin(Builtin):
    def __init__(self):
        super(ExitBuiltin, self).__init__('exit', nostatus=True)

    @streamtypes(None, None)
    @locality('local')
    def execute(self, context):
        context.hotwire.remote_exit()
        return []
BuiltinRegistry.getInstance().register(ExitBuiltin())
