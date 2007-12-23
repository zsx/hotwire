# This file is part of the Hotwire Shell user interface.
#   
# Copyright (C) 2007 Colin Walters <walters@verbum.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os, stat, signal, datetime, logging
from StringIO import StringIO

import gtk, gobject, pango

import hotwire
import hotwire_ui.widgets as hotwidgets
from hotwire.command import Pipeline
from hotwire.fs import FilePath, unix_basename
from hotwire_ui.render import TreeObjectsRenderer, ClassRendererMapping, menuitem
from hotwire.sysdep.fs import Filesystem, File
from hotwire.logutil import log_except
from hotwire_ui.pixbufcache import PixbufCache
from hotwire.util import format_file_size, quote_arg
from hotwire.externals.dispatch import dispatcher

_logger = logging.getLogger("hotwire.ui.render.File")

class FilePathRenderer(TreeObjectsRenderer):
    def __init__(self, *args, **kwargs):
        if not 'column_types' in kwargs.iterkeys():
            kwargs['column_types'] = [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT]
        self.__fs = Filesystem.getInstance()
        self.__basedir = None            
        super(FilePathRenderer, self).__init__(*args,
                                               **kwargs)
        self._table.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                            [('text/uri-list', 0, 0)],
                                            gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)
        #self._table.enable_model_drag_dest([('text/uri-list', 0, 0)],
        #                                    gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)        
        self._table.connect("drag-data-get", self.__on_drag_data_get)
        #self._table.connect("drag-data-received", self.__on_drag_data_received)

    def _setup_icon_path_columns(self):
        colidx = self._table.insert_column_with_data_func(-1, '',
                                                       gtk.CellRendererPixbuf(),
                                                       self._render_icon)
        col = self._table.get_column(colidx-1)
        col.set_spacing(0)
        colidx = self._table.insert_column_with_data_func(-1, _('Path'),
                                                          hotwidgets.CellRendererLink(underline=pango.UNDERLINE_NONE,
                                                                                      family='Monospace'),
                                                          self._render_objtext)
        col = self._table.get_column(colidx-1)
        col.set_spacing(0)
        col.set_resizable(True)
        self._linkcolumns.append(col)
    
    def _setup_view_columns(self):
        self._setup_icon_path_columns()
        colidx = self._table.insert_column_with_data_func(-1, _('Size'),
                                                           hotwidgets.CellRendererText(family='Monospace'),
                                                           self._render_size)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)
        colidx = self._table.insert_column_with_data_func(-1, _('Last Modified'),
                                                           hotwidgets.CellRendererText(family='Monospace'),
                                                           self._render_last_modified)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)
        if self.__fs.supports_owner():
            colidx = self._table.insert_column_with_data_func(-1, _('Owner'),
                                                              hotwidgets.CellRendererText(family='Monospace'),
                                                              self._render_owner)
            col = self._table.get_column(colidx-1)
            col.set_resizable(True)      
        if self.__fs.supports_group():
            colidx = self._table.insert_column_with_data_func(-1, _('Group'),
                                                              hotwidgets.CellRendererText(family='Monospace'),
                                                              self._render_group)
            col = self._table.get_column(colidx-1)
            col.set_resizable(True)
        colidx = self._table.insert_column_with_data_func(-1, _('Permissions'),
                                                           hotwidgets.CellRendererText(family='Monospace'),
                                                           self._render_permissions)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)  
        colidx = self._table.insert_column_with_data_func(-1, _('File Type'),
                                                           hotwidgets.CellRendererText(family='Monospace'),
                                                           self._render_mime)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)                

    def _file_for_iter(self, model, iter):
        return model.get_value(iter, 1)

    def _render_icon(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        icon_name = obj.icon
        if icon_name:
            if icon_name.startswith(os.sep):
                pixbuf = PixbufCache.getInstance().get(icon_name)
                cell.set_property('pixbuf', pixbuf)
            else:
                cell.set_property('icon-name', icon_name)
        else:
            cell.set_property('icon-name', None)

    def _render_objtext(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        path = obj.path
        if self.__basedir:
            text = unix_basename(path)
        else:
            text = path
        cell.set_text(text)

    def _render_size(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        size = obj.get_size()
        if size is not None: 
            cell.set_property('text', format_file_size(size))
        else:
            cell.set_property('text', '')

    def _render_last_modified(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        mtime = obj.get_mtime()
        if mtime is not None:
            dt = datetime.datetime.fromtimestamp(mtime) 
            cell.set_property('text', dt.isoformat(' '))
        else:
            cell.set_property('text', '')

    def _render_owner(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        cell.set_property('text', obj.get_owner() or '')

    def _render_group(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        cell.set_property('text', obj.get_group() or '')
            
    def _render_permissions(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        perms = obj.get_permissions_string()
        cell.set_property('text', perms or '')
        
    def _render_mime(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        mime = obj.get_mime()
        cell.set_property('text', mime or '')

    def _get_row(self, obj):
        if isinstance(obj, File):
            fobj = obj
        else:
            fobj = self.__fs.get_file(obj)
        dispatcher.connect(log_except(_logger)(self._signal_obj_changed), sender=fobj)
        return (fobj.path, fobj)
    
    def append_obj(self, obj, **kwargs):
        row = self._get_row(obj)
        if self.__basedir is not False:
            bn,fn = os.path.split(row[1].path)
            if self.__basedir is None:
                self.__basedir = bn
            elif bn == self.__basedir:
                pass
            else:
                self.__basedir = False
        self._model.append(row)

    def _onclick_iter(self, iter):
        self.__do_open(self._file_for_iter(self._model, iter))
        return True

    def __do_open(self, obj):
        if obj.is_directory(follow_link=True):
            self.context.do_cd(obj.path)
        else:    
            self.__fs.launch_open_file(obj.path, self.context.get_cwd())        

    def _get_menuitems(self, iter):
        fobj = self._file_for_iter(self._model, iter)
        items = self.__fs.get_file_menuitems(fobj, context=self.context)
        items.append(gtk.SeparatorMenuItem())
        if fobj.is_directory():
            menuitem = gtk.MenuItem(_('Open Folder in New Tab'))
            menuitem.connect('activate', self.__on_new_tab_activated, fobj.path)
            items.append(menuitem)
            menuitem = gtk.MenuItem(_('Open Folder in New Window'))
            menuitem.connect('activate', self.__on_new_window_activated, fobj.path)
            items.append(menuitem)            
            items.append(gtk.SeparatorMenuItem())
        menuitem = gtk.MenuItem(_('Move to Trash'))
        menuitem.connect("activate", self.__on_remove_activated, fobj.path)
        items.append(menuitem)
        return items
       
    def __on_new_tab_activated(self, menu, path):
        _logger.debug("got new tab for %s", path)
        from hotwire_ui.shell import locate_current_window
        hwin = locate_current_window(self._table)
        hwin.new_tab_hotwire(initcwd=path, initcmd='ls')  
        
    def __on_new_window_activated(self, menu, path):
        _logger.debug("got new window for %s", path)
        from hotwire_ui.shell import locate_current_window
        hwin = locate_current_window(self._table)
        hwin.new_win_hotwire(initcwd=path, initcmd='ls')
        
    def __on_remove_activated(self, menu, path):
        _logger.debug("got remove for %s", path)
        from hotwire_ui.shell import locate_current_shell
        hw = locate_current_shell(self._table)    
        hw.internal_execute('rm', path)           

    def __on_drag_data_get(self, tv, context, selection, info, timestamp):
        sel = tv.get_selection()
        model, paths = sel.get_selected_rows()
        _logger.debug("got selection %s %s", model, paths)
        obuf = StringIO()
        for path in paths:
            iter = model.get_iter(path)
            fobj = self._file_for_iter(model, iter)
            obuf.write(fobj.path)
            obuf.write('\r\n')
        selection.set('text/uri-list', 8, obuf.getvalue())

    def __on_drag_data_received(self, tv, context, x, y, selection, info, etime):
        model = tv.get_model()
        sel_data = selection.data
        from hotwire_ui.shell import locate_current_shell
        hw = locate_current_shell(self._table)
        hw.do_copy_url_drag_to_dir(sel_data, self.context.get_cwd())

ClassRendererMapping.getInstance().register(File, FilePathRenderer)
ClassRendererMapping.getInstance().register(FilePath, FilePathRenderer)
