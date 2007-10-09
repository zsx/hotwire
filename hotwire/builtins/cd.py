import os, sys, stat

from hotwire.builtin import Builtin, BuiltinRegistry, OutputStreamSchema
from hotwire.fs import FilePath, DirectoryGenerator
from hotwire.completion import CdCompleter 

class CdBuiltin(Builtin):
    """Change working directory and list its contents."""
    def __init__(self):
        super(CdBuiltin, self).__init__('cd',
                                        output=OutputStreamSchema(FilePath),
                                        parseargs='str',
                                        idempotent=True,
                                        threaded=True)

    def get_completer(self, argpos, context):
        return CdCompleter.getInstance()

    def execute(self, context, dir=None):
        if not dir:
            target_dir = os.path.expanduser("~")
        else:
            target_dir = dir
        new_dir = context.hotwire.chdir(target_dir)
        for result in BuiltinRegistry.getInstance()['ls'].execute(context, [new_dir]):
            yield result
BuiltinRegistry.getInstance().register(CdBuiltin())
