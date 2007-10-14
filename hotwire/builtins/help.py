from hotwire.builtin import Builtin, BuiltinRegistry

class HelpItem(object):
    pass

class HelpBuiltin(Builtin):
    """Display help."""
    def __init__(self):
        super(HelpBuiltin, self).__init__('help',
                                          output=HelpItem,
                                          idempotent=True)

    def execute(self, context):
        yield HelpItem()
    
BuiltinRegistry.getInstance().register(HelpBuiltin())
