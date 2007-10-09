import os, os.path, stat

from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry
from hotwire.sysdep.fs import Filesystem

class EditBuiltin(Builtin):
    """Launch the text editor."""
    def __init__(self):
        super(EditBuiltin, self).__init__('edit',nostatus=True,
                                          parseargs='shglob',
                                          idempotent=True)
 
    def execute(self, context, args):
        fs = Filesystem.getInstance()
        for arg in args:
            fs.launch_edit_file(arg)
        return []
BuiltinRegistry.getInstance().register(EditBuiltin())
