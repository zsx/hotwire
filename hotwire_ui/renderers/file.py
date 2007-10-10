import os, stat, signal, datetime

import gtk, gobject, pango

import hotwire
import hotwire_ui.widgets as hotwidgets
from hotwire.fs import FilePath, unix_basename
from hotwire_ui.render import TreeObjectsRenderer, ClassRendererMapping, menuitem
from hotwire.sysdep.fs import Filesystem
from hotwire_ui.pixbufcache import PixbufCache
from hotwire.util import format_file_size

class FilePathRenderer(TreeObjectsRenderer):
    def __init__(self, *args, **kwargs):
        if not 'column_types' in kwargs.iterkeys():
            kwargs['column_types'] = [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT]
        self.__fs = Filesystem.getInstance()
        self.__basedir = None            
        super(FilePathRenderer, self).__init__(*args,
                                               **kwargs)

    def _setup_icon_path_columns(self):
        colidx = self._table.insert_column_with_data_func(-1, '',
                                                       gtk.CellRendererPixbuf(),
                                                       self._render_icon)
        col = self._table.get_column(colidx-1)
        col.set_spacing(0)
        colidx = self._table.insert_column_with_data_func(-1, 'Path',
                                                          hotwidgets.CellRendererLink(underline=pango.UNDERLINE_NONE),
                                                          self._render_objtext)
        col = self._table.get_column(colidx-1)
        col.set_spacing(0)
        col.set_resizable(True)
        self._linkcolumns.append(col)
    
    def _setup_view_columns(self):
        self._setup_icon_path_columns()
        colidx = self._table.insert_column_with_data_func(-1, 'Size',
                                                           hotwidgets.CellRendererText(),
                                                           self._render_size)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)
        colidx = self._table.insert_column_with_data_func(-1, 'Last Modified',
                                                           hotwidgets.CellRendererText(),
                                                           self._render_last_modified)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)
        if self.__fs.supports_owner():
            colidx = self._table.insert_column_with_data_func(-1, 'Owner',
                                                              hotwidgets.CellRendererText(),
                                                              self._render_owner)
            col = self._table.get_column(colidx-1)
            col.set_resizable(True)      
        if self.__fs.supports_group():
            colidx = self._table.insert_column_with_data_func(-1, 'Group',
                                                              hotwidgets.CellRendererText(),
                                                              self._render_group)
            col = self._table.get_column(colidx-1)
            col.set_resizable(True)
        colidx = self._table.insert_column_with_data_func(-1, 'Permissions',
                                                           hotwidgets.CellRendererText(),
                                                           self._render_permissions)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)  
        colidx = self._table.insert_column_with_data_func(-1, 'File Type',
                                                           hotwidgets.CellRendererText(),
                                                           self._render_mime)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)                

    def _file_for_iter(self, model, iter):
        return model.get_value(iter, 1)

    def _render_icon(self, col, cell, model, iter):
        obj = self._file_for_iter(model, iter)
        icon_name = self.__fs.get_file_icon_name(obj)
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
        file_obj = self.__fs.get_file(obj)
        file_obj.connect("changed", self._signal_obj_changed, 1)
        return (obj, file_obj)

    def append_obj(self, obj):
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
            self.__fs.launch_open_file(obj.path)        

    def _get_menuitems(self, iter):
        return self.__fs.get_file_menuitems(self._file_for_iter(self._model, iter))

ClassRendererMapping.getInstance().register(FilePath, FilePathRenderer)
