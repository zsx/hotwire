import os, sys, shutil, stat

import hotwire
import hotwire.fs
from hotwire.fs import FilePath

from hotwire.builtin import Builtin, BuiltinRegistry  
from hotwire.builtins.fileop import FileOpBuiltin

class MkdirBuiltin(FileOpBuiltin):
    """Create directories."""
    def __init__(self):
        super(MkdirBuiltin, self).__init__('mkdir',
                                           parseargs='shglob',
                                           hasstatus=True,
                                           threaded=True)

    def execute(self, context, args):
        if not args:
            raise ValueError("Need directory to create")
        sources_total = len(args)
        for i,arg in enumerate(args):
            arg_path = FilePath(arg, context.cwd)
            try:
                os.makedirs(arg_path)
            except OSError, e:
                pass
            self._status_notify(context, sources_total, i+1)

        return []
BuiltinRegistry.getInstance().register(MkdirBuiltin())
