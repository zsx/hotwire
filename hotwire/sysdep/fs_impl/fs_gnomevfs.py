import os,sys,subprocess,logging

import gtk, gnomevfs, gobject
import gnome.ui

from hotwire.sysdep.fs_impl.fs_unix import UnixFilesystem, UnixFile

_logger = logging.getLogger("hotwire.fs.GnomeVfs")

class GnomeVfsFile(UnixFile):
    def __init__(self, path):
        super(GnomeVfsFile, self).__init__(path)
        self.vfsstat = None
        self.target_vfsstat = None
        self.uri = gnomevfs.get_uri_from_local_path(path) 

    def is_directory(self, follow_link=False):
        if not self.vfsstat:
            return False
        if follow_link and self.vfsstat.type == gnomevfs.FILE_TYPE_SYMBOLIC_LINK:
            stbuf = self.target_vfsstat
        else:
            stbuf = self.vfsstat
        return stbuf and (stbuf.type == gnomevfs.FILE_TYPE_DIRECTORY)

    def get_size(self):
        return self.vfsstat and self.vfsstat.size

    def get_mtime(self):
        return self.vfsstat and self.vfsstat.mtime
    
    def get_mode(self):
        return self.vfsstat and self.vfsstat.type
    
    def get_permissions(self):
        return self.vfsstat and self.vfsstat.permissions
    
    def get_uid(self):
        return self.vfsstat and self.vfsstat.uid
    
    def get_gid(self):
        return self.vfsstat and self.vfsstat.gid
    
    def get_mime(self):
        return self.vfsstat and self.vfsstat.mime_type
            
    def get_file_type_char(self):
        vfsstat = self.vfsstat
        if vfsstat.type == gnomevfs.FILE_TYPE_REGULAR:
            return '-'
        elif vfsstat.type == gnomevfs.FILE_TYPE_DIRECTORY:
            return 'd'
        elif vfsstat.type == gnomevfs.FILE_TYPE_SYMBOLIC_LINK:
            return 'l'
        else:
            return '?'       
            
    def _do_get_stat(self):
        try:
            self.vfsstat = gnomevfs.get_file_info(self.uri, gnomevfs.FILE_INFO_GET_MIME_TYPE)
            if self.vfsstat.type == gnomevfs.FILE_TYPE_SYMBOLIC_LINK:
                try:
                    self.target_vfsstat = gnomevfs.get_file_info(self.uri, gnomevfs.FILE_INFO_GET_MIME_TYPE | gnomevfs.FILE_INFO_FOLLOW_LINKS)
                except gnomevfs.NotFoundError, e:
                    _logger.debug("Failed to get file info for target of '%s'", self.uri, exc_info=True)
        except gnomevfs.NotFoundError, e:
            _logger.debug("Failed to get file info for '%s'", self.uri, exc_info=True)

class GnomeVFSFilesystem(UnixFilesystem):
    def __init__(self):
        super(GnomeVFSFilesystem, self).__init__()
        self.__thumbnails = gnome.ui.ThumbnailFactory(gnome.ui.THUMBNAIL_SIZE_NORMAL)
        self.__itheme = gtk.icon_theme_get_default() 
        _logger.debug("gnomevfs initialized")

    def get_file(self, path):
        fobj = GnomeVfsFile(path)
        fobj.get_stat()
        return fobj
    
    def get_file_icon_name(self, file_obj):
        if not file_obj.vfsstat:
            return None
        try:
            (result, flags) = gnome.ui.icon_lookup(self.__itheme, self.__thumbnails, file_obj.uri, file_info=file_obj.vfsstat, mime_type=file_obj.vfsstat.mime_type)
        except gnomevfs.NotFoundError, e:
            _logger.debug("Failed to get file info for '%s'", file_obj.uri, exc_info=True)
            return None
        return result
    
    def launch_open_file(self, path):
        _logger.debug("calling gnome-open '%s'", path)
        # the easy way
        subprocess.call(['gnome-open', path])

    def __launch_vfsmimeapp(self, app, uri):
        if uri.startswith('file://'):
            uri = gnomevfs.get_local_path_from_uri(uri)
        if hasattr(gnomevfs, 'mime_application_launch'):
            gnomevfs.mime_application_launch(app, uri)
        else:
            exec_components = app[2].split(' ')
            replaced_f = False
            for i,component in enumerate(exec_components):
                if component == '%f':
                    exec_components[i] = uri
                    replaced_f = True
            if not replaced_f:
                exec_components.append(uri)
            subprocess.Popen(exec_components, stdout=sys.stdout, stderr=sys.stderr)        

    def launch_edit_file(self, path):
        uri = gnomevfs.get_uri_from_local_path(path) 
        app = gnomevfs.mime_get_default_application("text/plain")
        self.__launch_vfsmimeapp(app, uri)

    def __on_appmenu_activated(self, menu, app, uri):
        self.__launch_vfsmimeapp(app, uri)

    def get_file_menuitems(self, file_obj):
        uri = gnomevfs.get_uri_from_local_path(file_obj.path)
        vfsstat = gnomevfs.get_file_info(uri, gnomevfs.FILE_INFO_GET_MIME_TYPE)
        apps = gnomevfs.mime_get_all_applications(vfsstat.mime_type)
        textapp = gnomevfs.mime_get_default_application("text/plain")
        menuitems = []
        def add_menuitem(app):
            menuitem = gtk.MenuItem('Open with %s' % (app[1],))
            menuitem.connect("activate", self.__on_appmenu_activated, app, uri)
            menuitems.append(menuitem) 
        for app in apps:
            add_menuitem(app)
        add_textapp = (not file_obj.is_directory(follow_link=True)) and (textapp not in apps)
        if apps and add_textapp:
            menuitems.append(gtk.SeparatorMenuItem())
        if add_textapp:
            add_menuitem(textapp)
        return menuitems

def getInstance():
    return GnomeVFSFilesystem()
