import os, sys, stat

from hotwire.builtin import Builtin, BuiltinRegistry, OutputStreamSchema, parseargs, idempotent
from hotwire.fs import FilePath, DirectoryGenerator
from hotwire.completion import CdCompleter 

class CdBuiltin(Builtin):
    """Change working directory and list its contents."""
    def __init__(self):
        super(CdBuiltin, self).__init__('cd',
                                        output=OutputStreamSchema(FilePath))

    def get_completer(self, argpos, context):
        return CdCompleter.getInstance()

    @parseargs('str')
    @idempotent()
    def execute(self, context, dir=None):
        if not dir:
            target_dir = os.path.expanduser("~")
        else:
            target_dir = dir
        new_dir = context.hotwire.chdir(target_dir)
        context.push_undo(lambda: context.hotwire.do_cd(context.cwd)) 
        for result in BuiltinRegistry.getInstance()['ls'].execute(context, [new_dir]):
            yield result
BuiltinRegistry.getInstance().register(CdBuiltin())
