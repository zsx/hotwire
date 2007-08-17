from hotwire import FilePath
from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry, streamtypes, locality

class LcdBuiltin(Builtin):
    def __init__(self):
        super(LcdBuiltin, self).__init__('lcd')

    @streamtypes(None, FilePath)
    @locality('local')
    def execute(self, context, dir):
        dir = context.hotwire.chdir(dir)
        generator = iterdir(dir)
        for x in generator:
            yield FilePath(x, dir)
BuiltinRegistry.getInstance().register(LcdBuiltin())
