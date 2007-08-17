from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry, OutputStreamSchema

class HistoryBuiltin(Builtin):
    def __init__(self):
        super(HistoryBuiltin, self).__init__('history',
                                             output=OutputStreamSchema(str))

    def execute(self, context):
        return context.hotwire.get_history()
    
BuiltinRegistry.getInstance().register(HistoryBuiltin())
