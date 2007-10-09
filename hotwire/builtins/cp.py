import os, sys, shutil, stat

import hotwire
import hotwire.fs
from hotwire.fs import FilePath

from hotwire.builtin import Builtin, BuiltinRegistry  
from hotwire.builtins.fileop import FileOpBuiltin

class CpBuiltin(FileOpBuiltin):
    """Copy sources to destination."""
    def __init__(self):
        super(CpBuiltin, self).__init__('cp', aliases=['copy'],
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
            raise ValueError("Can't copy multiple items to non-directory")
        sources_total = len(sources)
        self._status_notify(context, sources_total, 0)

        if target_is_dir:
            for i,source in enumerate(sources):
                hotwire.fs.copy_file_or_dir(FilePath(source, context.cwd), target, True)
                self._status_notify(context, sources_total, i+1)
        else:
            hotwire.fs.copy_file_or_dir(FilePath(sources[0], context.cwd), target, False)
            self._status_notify(context, sources_total, 1)
            
        return []
BuiltinRegistry.getInstance().register(CpBuiltin())
