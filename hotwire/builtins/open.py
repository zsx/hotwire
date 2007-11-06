import hotwire
from hotwire.builtin import Builtin, BuiltinRegistry
from hotwire.fs import FilePath
from hotwire.sysdep.fs import Filesystem

class OpenBuiltin(Builtin):
    """Open a file using default platform action."""
    def __init__(self):
        super(OpenBuiltin, self).__init__('open', 
                                          idempotent=True,
                                          nostatus=True,                                          
                                          parseargs='shglob')

    def execute(self, context, args):
        fs = Filesystem.getInstance()
        for arg in args:
            fs.launch_open_file(FilePath(arg, context.cwd))
        return [] 

BuiltinRegistry.getInstance().register(OpenBuiltin())
