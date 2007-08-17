import os, sys

from hotwire.builtin import Builtin

class FileOpBuiltin(Builtin):
    def _status_notify(self, context, total, count):
        context.status_notify('%d/%d files' % (count,total), int(100*(count*1.0/total)))
