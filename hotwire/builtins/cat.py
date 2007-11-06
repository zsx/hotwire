import os,sys,pickle

from hotwire.fs import FilePath

from hotwire.builtin import Builtin, BuiltinRegistry

class CatBuiltin(Builtin):
    """Concatenate files."""
    def __init__(self):
        super(CatBuiltin, self).__init__('cat',
                                         output=str, # 'any'
                                         parseargs='shglob',
                                         idempotent=True,
                                         #options=[['-p', '--pickle'],],                                          
                                         threaded=True)

    def execute(self, context, args, options=[]):
        do_unpickle = '-p' in options
        for f in args:
            fpath = FilePath(f, context.cwd)
            if do_unpickle:
                for v in pickle.load(open(fpath, 'rb')): 
                    yield v
            else:
                for line in open(fpath, 'rU'):
                    yield line[0:-1]
BuiltinRegistry.getInstance().register(CatBuiltin())
