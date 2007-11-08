import os, sys

from hotwire.builtin import Builtin

class FileOpBuiltin(Builtin):
    def _note_modified_paths(self, context, paths):
        first_dn = os.path.dirname(paths[0])
        all_matches = True
        for path in paths[1:]:
            dn = os.path.dirname(path)
            if dn != first_dn:
                all_matches = False
        if all_matches:
            context.metadata('hotwire.fileop.basedir', 0, first_dn)
            
    def _status_notify(self, context, total, count):
        context.status_notify('%d/%d files' % (count,total), int(100*(count*1.0/total)))
