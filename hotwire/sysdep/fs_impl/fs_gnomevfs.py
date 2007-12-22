# This file is part of the Hotwire Shell project API.

# Copyright (C) 2007 Colin Walters <walters@verbum.org>

# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies 
# of the Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all 
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE 
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR 
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os,sys,subprocess,logging

import gtk, gnomevfs, gobject
import gnome.ui

from hotwire.sysdep.fs import FileStatError
from hotwire.sysdep.fs_impl.fs_unix import UnixFilesystem, UnixFile

_logger = logging.getLogger("hotwire.fs.GnomeVfs")

class GnomeVfsFile(UnixFile):
    def __init__(self, path, **kwargs):
        super(GnomeVfsFile, self).__init__(path, **kwargs)
        self.vfsstat = None
        self.target_vfsstat = None
        self.target_vfsstat_error = None
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
            
    def _do_get_stat(self, rethrow=False):
        try:
            self.vfsstat = gnomevfs.get_file_info(self.uri, gnomevfs.FILE_INFO_GET_MIME_TYPE | gnomevfs.FILE_INFO_FORCE_FAST_MIME_TYPE)
            if self.vfsstat.type == gnomevfs.FILE_TYPE_SYMBOLIC_LINK:
                try:
                    self.target_vfsstat = gnomevfs.get_file_info(self.uri, gnomevfs.FILE_INFO_GET_MIME_TYPE | gnomevfs.FILE_INFO_FOLLOW_LINKS)
                except Exception, e:
                    _logger.debug("Failed to get file info for target of '%s'", self.uri, exc_info=True)
                    self.target_vfsstat_error = str(e)
        except Exception, e:
            _logger.debug("Failed to get file info for '%s'", self.uri, exc_info=True)
            self.stat_error = str(e)
            if rethrow:
                raise FileStatError(e)
            
    def _do_get_icon(self):
        if not self.vfsstat:
            self.icon = 'gtk-dialog-error'
        try:
            self.icon = self.fs.icon_lookup(self)
        except Exception, e:
            _logger.debug("Failed to get file icon for '%s'", self.uri, exc_info=True)
            self.icon = 'gtk-dialog-error'

class GnomeVfsMonitor(object):
    """Avoid some locking oddities in gnomevfs monitoring"""
    def __init__(self, path, montype, cb):
        super(GnomeVfsMonitor, self).__init__()
        self.__path = path
        self.__cb = cb
        self.__idle_id = 0
        self.__monid = gnomevfs.monitor_add(path, montype, self.__on_vfsmon)
  
    def __idle_emit(self):
        self.__idle_id = 0
        self.__cb()

    def __on_vfsmon(self, *args):
        if not self.__monid:
            return
        if self.__idle_id == 0:
            self.__idle_id = gobject.timeout_add(300, self.__idle_emit)

    def cancel(self):
        if self.__idle_id:
            gobject.source_remove(self.__idle_id)
            self.__idle_id = 0
        if self.__monid:
            gnomevfs.monitor_cancel(self.__monid)
            self.__monid = Nones

class GnomeVFSFilesystem(UnixFilesystem):
    def __init__(self):
        super(GnomeVFSFilesystem, self).__init__()
        self.fileklass = GnomeVfsFile        
        self.__thumbnails = gnome.ui.ThumbnailFactory(gnome.ui.THUMBNAIL_SIZE_NORMAL)
        self.__itheme = gtk.icon_theme_get_default() 
        _logger.debug("gnomevfs initialized")

    def get_monitor(self, path, cb):
        return GnomeVfsMonitor(path, gnomevfs.MONITOR_EVENT_CHANGED, cb)
    
    def icon_lookup(self, fobj):
        (result, flags) = gnome.ui.icon_lookup(self.__itheme, self.__thumbnails, fobj.uri, file_info=fobj.vfsstat, mime_type=fobj.vfsstat.mime_type)
        return result        
    
    def launch_open_file(self, path, cwd=None):
        _logger.debug("calling gnome-open '%s'", path)
        # the easy way 
        subprocess.call(['gnome-open', path], cwd=cwd)

    def __launch_vfsmimeapp(self, app, uri, cwd=None):
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
            subprocess.Popen(exec_components, stdout=sys.stdout, stderr=sys.stderr, cwd=cwd)        

    def launch_edit_file(self, path):
        uri = gnomevfs.get_uri_from_local_path(path) 
        app = gnomevfs.mime_get_default_application("text/plain")
        self.__launch_vfsmimeapp(app, uri)

    def __on_appmenu_activated(self, menu, app, uri, context=None):
        self.__launch_vfsmimeapp(app, uri, cwd=(context and context.get_cwd()))

    def get_file_menuitems(self, file_obj, context=None):
        uri = gnomevfs.get_uri_from_local_path(file_obj.path)
        vfsstat = gnomevfs.get_file_info(uri, gnomevfs.FILE_INFO_GET_MIME_TYPE)
        apps = gnomevfs.mime_get_all_applications(vfsstat.mime_type)
        textapp = gnomevfs.mime_get_default_application("text/plain")
        menuitems = []
        def add_menuitem(app):
            menuitem = gtk.MenuItem('Open with %s' % (app[1],))
            menuitem.connect("activate", self.__on_appmenu_activated, app, uri, context)
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
