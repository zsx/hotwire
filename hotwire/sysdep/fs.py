# -*- tab-width: 4 -*-
import os,sys,shutil,stat,platform,logging
from cStringIO import StringIO

import gobject

import hotwire
from hotwire.fs import unix_basename
from hotwire.async import MiniThreadPool
import hotwire.sysdep.fs_impl

_logger = logging.getLogger("hotwire.sysdep.Filesystem")

class BaseFilesystem(object):
    def __init__(self):
        self._trashdir = os.path.expanduser('~/.Trash')
        self.makedirs_p(self._trashdir)

    def get_basename_is_ignored(self, bn):
        return bn.startswith('.')

    def get_file(self, path):
        f = File(path)
        f.get_stat()
        return f
        
    def get_file_icon_name(self, file_obj):
        if file_obj.stat_error or not file_obj.stat:
            return None
        elif stat.S_ISDIR(file_obj.stat.st_mode):
            return 'gtk-directory'
        return 'gtk-file'

    def launch_open_file(self, path):
        raise NotImplementedError()

    def launch_edit_file(self, path):
        raise NotImplementedError()

    def get_file_menuitems(self, file_obj):
        return []

    def get_conf_dir(self):
        raise NotImplementedError()
    
    def get_path_generator(self):
        raise NotImplementedError()

    def _default_x_filter(self, path, stbuf=None):
        try:
            buf = stbuf or os.stat(path)
        except OSError, e:
            return False
        return stat.S_ISREG(buf.st_mode) and os.access(path, os.X_OK)

    def get_executable_filter(self):
        return self._default_x_filter

    def move_to_trash(self, path):
        bn = unix_basename(path)
        newf = os.path.join(self._trashdir, bn)
        try:
            statbuf = os.stat(newf) 
        except OSError, e:
            statbuf = None
        if statbuf:
            _logger.debug("Removing from trash: %s", newf) 
            if stat.S_ISDIR(statbuf.st_mode):
                shutil.rmtree(newf, onerror=lambda f,p,e:_logger.exception("Failed to delete '%s' from trash", newf))
        shutil.move(path, newf)

    def get_trash_item(self, name):
		return os.path.join(self._trashdir, name)

    def undo_trashed(self, args):
        for arg in args:
            trashed = self.get_trash_item(unix_basename(arg))
            if trashed:
                shutil.move(trashed, arg)

    def makedirs_p(self, path):
        try:
            os.makedirs(path)
        except OSError, e:
            # hopefully it was EEXIST...
            pass
        return path
    
    def supports_owner(self):
        return False
    
    def supports_group(self):
        return False   

class File(gobject.GObject):
    __gsignals__ = {
        "changed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, path):
        super(File, self).__init__()
        self.path = path
        self.stat = None
        self.__permstring = None
        self.target_stat = None
        self.stat_error = None

    def is_directory(self, follow_link=False):
        if not self.stat:
			return False
        if follow_link and self.stat.S_ISLNK(self.stat.st_mode):
			stbuf = self.target_stat
        else:
			stbuf = self.stat
        return stbuf and stat.S_ISDIR(stbuf.st_mode)

    def get_size(self):
        if self.stat and stat.S_ISREG(self.stat.st_mode):
            return self.stat.st_size
        return None

    def get_mtime(self):
        if self.stat:
            return self.stat.st_mtime
        return None
    
    def get_mode(self):
        return self.stat and self.stat.st_mode
    
    def get_permissions(self):
        return self.stat and self.stat.st_mode
    
    def get_file_type_char(self):
        if self.is_directory():
            return 'd'
        return '-'    

    def get_permissions_string(self):
        if self.__permstring:
            return self.__permstring
        
        perms = self.get_permissions()
        if not perms:
            return
        buf = StringIO()
                
        buf.write(self.get_file_type_char())
        
        if perms & stat.S_ISUID: buf.write('s')
        elif perms &stat.S_IRUSR: buf.write('r')
        else: buf.write('-')
        if perms & stat.S_IWUSR: buf.write('w')
        else: buf.write('-')
        if perms & stat.S_IXUSR: buf.write('x')
        else: buf.write('-')
        
        if perms & stat.S_ISGID: buf.write('s')
        elif perms & stat.S_IRGRP:buf.write('r')
        else: buf.write('-')
        if perms & stat.S_IWGRP: buf.write('w')
        else: buf.write('-')
        if perms & stat.S_IXGRP: buf.write('x')
        else: buf.write('-')
        
        if perms & stat.S_IROTH: buf.write('r')
        else: buf.write('-')
        if perms & stat.S_IWOTH: buf.write('w')
        else: buf.write('-')
        if perms & stat.S_IXOTH: buf.write('x')
        else: buf.write('-')
        
        self.__permstring = buf.getvalue()
        return self.__permstring

    def get_stat(self):
        self._get_stat_async()

    def _get_stat_async(self):
        MiniThreadPool.getInstance().run(self.__get_stat_signal)

    def _do_get_stat(self):
        try:
            self.stat = hasattr(os, 'lstat') and os.lstat(self.path) or os.stat(self.path)
            if stat.S_ISLNK(self.stat.st_mode):
				try:
					self.target_stat = os.stat(self.path)
				except OSError, e:
					self.target_stat = None		
        except OSError, e:
            _logger.debug("Failed to stat '%s': %s", self.path, e)
            self.stat_error = str(e)

    def __get_stat_signal(self):
        self._do_get_stat()
        gobject.idle_add(lambda: self.emit("changed"), priority=gobject.PRIORITY_LOW)

_module = None
if platform.system() == 'Linux':
    try:
        import hotwire.sysdep.fs_impl.fs_gnomevfs
        _module = hotwire.sysdep.fs_impl.fs_gnomevfs
    except:
        import hotwire.sysdep.fs_impl.fs_unix
        _module = hotwire.sysdep.fs_impl.fs_unix
elif platform.system() == 'Windows':
    import hotwire.sysdep.fs_impl.fs_win32
    _module = hotwire.sysdep.fs_impl.fs_win32
else:
    raise NotImplementedError("No Filesystem implemented for %s!" % (platform.system(),))

_instance = None
class Filesystem(object):
    @staticmethod
    def getInstance():
        global _instance
        if _instance is None:
            _instance = _module.getInstance()
        return _instance
