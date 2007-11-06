from hotwire.builtin import Builtin, BuiltinRegistry

class PyBuiltin(Builtin):
    """Process objects using Python code."""
    def __init__(self):
        super(PyBuiltin, self).__init__('py', 
                                        nostatus=True)

    def execute(self, context):
        context.hotwire.open_pyshell()
        return []
        
BuiltinRegistry.getInstance().register(PyBuiltin())
