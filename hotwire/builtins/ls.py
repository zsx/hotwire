import os, os.path, stat, logging, locale

from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema
from hotwire.fs import FilePath,DirectoryGenerator
from hotwire.sysdep.fs import Filesystem
from hotwire.util import xmap

_logger = logging.getLogger("hotwire.builtins.ls")

class LsBuiltin(Builtin):
    """List contents of a directory."""
    def __init__(self):
        super(LsBuiltin, self).__init__('ls', aliases=['dir'],
                                        input=InputStreamSchema(str, optional=True),
                                        output=FilePath,
                                        parseargs='shglob',
                                        idempotent=True,
                                        threaded=True,
                                        options=[['-l', '--long'],['-a', '--all']])

    def __ls_dir(self, dir, show_all):
        fs = Filesystem.getInstance()
        for x in DirectoryGenerator(dir):
            if show_all:
                yield x
            else:
                bn = os.path.basename(x)
                if not (fs.get_basename_is_ignored(bn)):
                    yield x

    def execute(self, context, args, options=[]):
        show_all = '-a' in options
        long_fmt = '-l' in options
            
        if len(args) in (0, 1):
            if len(args) == 1:
                arg0_path = FilePath(args[0], context.cwd)
                stbuf = os.stat(arg0_path)
            else:
                stbuf = None
                arg0_path = None
            if stbuf and stat.S_ISDIR(stbuf.st_mode):
                dir = arg0_path
            elif stbuf:
                yield arg0_path
                return
            else:
                dir = context.cwd
            generator = self.__ls_dir(dir, show_all)
        else:
            generator = xmap(lambda arg: FilePath(arg, context.cwd), args)
        generator = sorted(generator, locale.strcoll)
        for x in generator:
            yield x
BuiltinRegistry.getInstance().register(LsBuiltin())
