import os,sys,md5,sha

import hotwire
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema
from hotwire.fs import FilePath
from hotwire.sysdep.fs import Filesystem

class SecHashBuiltin(Builtin):
    """Create a secure hash from objects or file arguments"""
    def __init__(self):
        super(SecHashBuiltin, self).__init__('sechash', idempotent=True,
                                             input=InputStreamSchema('any', optional=True),
                                             output=str,
                                             parseargs='shglob',                                             
                                             options=[['-5', '--md5'],],
                                             threaded=True)

    def execute(self, context, args, options=[]):
        alg = ('-5' in options) and md5 or sha  
        fs = Filesystem.getInstance()
        if (not args) and context.input:
            for val in context.input:
                valstr = str(val)
                hashval = alg.new()
                hashval.update(valstr)
                yield hashval.hexdigest()
        for arg in args:
            fpath = FilePath(arg, context.cwd)
            stream = open(fpath)
            hashval = alg.new()
            buf = stream.read(4096)
            while buf:
                hashval.update(buf)
                buf = stream.read(4096)
            stream.close()
            yield hashval.hexdigest()

BuiltinRegistry.getInstance().register(SecHashBuiltin())
