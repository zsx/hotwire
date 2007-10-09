from hotwire.fs import FilePath

from hotwire.builtin import Builtin, BuiltinRegistry, OutputStreamSchema

class CatBuiltin(Builtin):
    """Concatenate files."""
    def __init__(self):
        super(CatBuiltin, self).__init__('cat',
                                         output=OutputStreamSchema(str),
                                         parseargs='shglob',
                                         idempotent=True,
                                         threaded=True)

    def execute(self, context, args):
        for f in args:
            for line in file(FilePath(f, context.hotwire.get_cwd()), 'r'):
                yield line[0:-1]
BuiltinRegistry.getInstance().register(CatBuiltin())
