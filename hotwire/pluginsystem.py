import os,sys,imp,logging

import hotwire
from hotwire.fs import DirectoryGenerator
from hotwire.sysdep.fs import Filesystem

_logger = logging.getLogger("hotwire.PluginSystem")

def load_plugins():
    custom_path = Filesystem.getInstance().makedirs_p(os.path.join(Filesystem.getInstance().get_conf_dir(), "plugins"))
    _load_plugins_in_dir(custom_path)
   
def _load_plugins_in_dir(dirname):
    if not os.path.isdir(dirname):
       return    
    for f in DirectoryGenerator(dirname):
        if f.endswith('.py'):
            fname = os.path.basename(f[:-3])
            try:
                _logger.debug("Attempting to load plugin: %s", f)
                (stream, path, desc) = imp.find_module(fname, [dirname])
                try:
                    imp.load_module(fname, stream, f, desc)
                finally:
                    stream.close()
            except:
                _logger.warn("Failed to load custom file: %s", f, exc_info=True)
                
 