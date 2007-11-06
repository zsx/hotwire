import os,sys,pickle

import hotwire
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema
from hotwire.fs import FilePath
from hotwire.sysdep.fs import Filesystem

class WriteBuiltin(Builtin):
    """Save stream to files."""
    def __init__(self):
        super(WriteBuiltin, self).__init__('write',
                                           input=InputStreamSchema('any', optional=False),
                                           parseargs='shglob',
                                           options=[['-a', '--append'],['-p', '--pickle']],                                           
                                           threaded=True)

    def execute(self, context, args, options=[]):
        open_mode = ('-a' in options) and 'a+' or 'w'
        do_pickle = '-p' in options
        if do_pickle:
            open_mode = 'wb'
        if not context.input:
            return
        streams = map(lambda x: open(FilePath(x, context.cwd), open_mode), args)
        if not do_pickle:
            for arg in context.input:
                for stream in streams:
                    stream.write('%s\n' % (str(arg),))
        else:
            # Kind of annoying pickle makes you do this.
            arglist = list(context.input)
            for stream in streams:
                pickle.dump(arglist, stream)
        map(lambda x: x.close(), streams)
        return []

BuiltinRegistry.getInstance().register(WriteBuiltin())
