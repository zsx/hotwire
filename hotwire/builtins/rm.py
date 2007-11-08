import os, shutil

import hotwire
from hotwire.fs import FilePath, unix_basename
from hotwire.sysdep.fs import Filesystem

from hotwire.builtin import BuiltinRegistry
from hotwire.builtins.fileop import FileOpBuiltin

class RmBuiltin(FileOpBuiltin):
    """Move a file to the trash."""
    def __init__(self):
        super(RmBuiltin, self).__init__('rm', aliases=['delete'],
                                        parseargs='shglob',
                                        undoable=True,
                                        hasstatus=True,
                                        threaded=True)

    def execute(self, context, args):
        sources = map(lambda arg: FilePath(arg, context.cwd), args) 
        sources_total = len(sources)
        undo_targets = []
        self._status_notify(context, sources_total, 0)
        fs = Filesystem.getInstance()
        try:
            for i,arg in enumerate(sources):
                fs.move_to_trash(arg)
                undo_targets.append(arg)
                self._status_notify(context,sources_total,i+1)
                self._note_modified_paths(context, sources)
        finally:
            context.push_undo(lambda: fs.undo_trashed(undo_targets))
        return []
BuiltinRegistry.getInstance().register(RmBuiltin())
