from hotwire.sysdep import is_unix,is_windows
from hotwire.sysdep.fs import Filesystem

def load():
    if is_unix():
        import hotwire_ui.adaptors.aliases_unix
        fs = Filesystem.getInstance()
        if fs.executable_on_path('hotwire-ssh'):
            import hotwire_ui.adaptors.ssh
        
    
    