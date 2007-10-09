import os, sys, shutil, stat

import hotwire
from hotwire.fs import FilePath, unix_basename

from hotwire.builtin import BuiltinRegistry
from hotwire.builtins.fileop import FileOpBuiltin

class MvBuiltin(FileOpBuiltin):
    """Rename initial arguments to destination."""
    def __init__(self):
        super(MvBuiltin, self).__init__('mv', aliases=['move'],
                                        parseargs='shglob',
                                        hasstatus=True,
                                        threaded=True)

    def execute(self, context, args):
        if not args:
            raise ValueError("Need source and destination")
        target = FilePath(args[-1], context.cwd)
        try:
            target_is_dir = stat.S_ISDIR(os.stat(target).st_mode)
            target_exists = True
        except OSError, e:
            target_is_dir = False
            target_exists = False
        
        sources = args[:-1]
        if not sources:
            raise ValueError("Need source and destination")
        if (not target_is_dir) and len(sources) > 1:
            raise ValueError("Can't move multiple items to non-directory")

        sources_total = len(sources)
        self._status_notify(context, sources_total, 0)

        if target_is_dir:
            for i,source in enumerate(sources):
                target_path = FilePath(unix_basename(source), target)
                shutil.move(FilePath(source, context.cwd), target_path)
                self._status_notify(context, sources_total, i+1)
        else:
            shutil.move(FilePath(sources[0], context.cwd), target)
            self._status_notify(context,sources_total,1)
            
        return []
BuiltinRegistry.getInstance().register(MvBuiltin())
