import sys, os, logging

import gtk, gobject

import hotwire
from hotwire.singletonmixin import Singleton
from hotwire_ui.pixbufcache import PixbufCache
import hotwire_ui.widgets as hotwidgets

_logger = logging.getLogger("hotwire.ui.Render")

def menuitem(name=None):
    def addtypes(f):
        setattr(f, 'hotwire_menuitem', name)
        return f
    return addtypes

class ClassRendererMapping(Singleton):
    def __init__(self):
        self.__map = {}

    def lookup(self, cls, context=None):
        try:
            return self.__map[cls](context=context)
        except KeyError:
            for base in cls.__bases__:
                result = self.lookup(base, context=context)
                if result:
                    return result
        return None

    def register(self, cls, target_class):
        self.__map[cls] = target_class

class ObjectsRenderer(gobject.GObject):  
    def __init__(self, context):
        super(ObjectsRenderer, self).__init__()
        self.context = context

    def get_widget(self):
        raise NotImplementedError()

    def get_opt_formats(self):
        return []

    def append_obj(self, obj, **kwargs):
        raise NotImplementedError()

    def get_autoscroll(self):
        return False

    def get_status_str(self):
        return None

    def get_objects(self):
        raise NotImplementedError()

    def get_search(self):
        raise NotImplementedError()
    
    def do_copy(self):
        return False
    
    def supports_input(self):
        return False
    
    def get_input(self):
        raise NotImplementedError()

class TreeObjectsRenderer(ObjectsRenderer):
    def __init__(self, context, column_types=None, **kwargs): 
        super(TreeObjectsRenderer, self).__init__(context, **kwargs)
        self.__search_enabled = False
        self._linkcolumns = []
        if column_types:
            ctypes = column_types
        else:
            ctypes = [gobject.TYPE_PYOBJECT]
        self.context = context
        self._model = self._create_model(ctypes)
        self._table = gtk.TreeView(self._model)
        #self._table.unset_flags(gtk.CAN_FOCUS)        
        self._table.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self._table.add_events(gtk.gdk.BUTTON_PRESS_MASK)        
        self._table.connect("button-press-event", self.__on_button_press)        
        self._table.connect("row-activated", self.__on_row_activated)
        self._setup_view_columns()
        for col in self._table.get_columns():
            col.set_resizable(True)

        self.__selected_obj = None

    def __get_func_menuitems(self, iter):
        menuitems = []
        for item in self.__class__.__dict__:
            attrval = getattr(self, item)
            if hasattr(attrval, '__call__'):
                if hasattr(attrval, 'hotwire_menuitem'):
                    name = getattr(attrval, 'hotwire_menuitem') or (attrval.func_name[0].upper() + attrval.func_name[1:])
                    menuitems.append((attrval, name))
        func_menuitems = []
        for (item, name) in menuitems:
            menuitem = gtk.MenuItem(label=name) 
            menuitem.connect("activate", self.__do_menuitem, item, iter)
            func_menuitems.append(menuitem)
        return func_menuitems

    def __do_menuitem(self, menuitem, func, iter):
        func(iter)
        self.context.push_msg('Execution of <b>%s</b> successful' % (gobject.markup_escape_text(func.func_name),),
                              markup=True)

    def get_search(self):
        res = gtk.bindings_activate(self._table, gtk.keysyms.f, gtk.gdk.CONTROL_MASK)
        return True

    def get_widget(self):
        return self._table

    def get_objects(self):
        iter = self._model.get_iter_first()
        while iter:
            val = self._model.get_value(iter, 0)
            yield val
            iter = self._model.iter_next(iter)

    def _create_model(self, column_types):
        return gtk.ListStore(*column_types)

    def _setup_view_columns(self):
        colidx = self._table.insert_column_with_data_func(-1, 'Object',
                                                       hotwidgets.CellRendererText(ellipsize=True),
                                                       self._render_objtext)
        col = self._table.get_column(colidx-1)
        col.set_resizable(True)

    def _insert_proptext(self, name, title=None, **kwargs):
        colidx = self._table.insert_column_with_data_func(-1, title or (name[0].upper() + name[1:]),
                                                          hotwidgets.CellRendererText(**kwargs),
                                                          self._render_proptext, name)
        col = self._table.get_column(colidx-1)
        col.set_data('hotwire-propname', name)
        col.set_data('hotwire-proptype', unicode)
        col.set_resizable(True)
        return col

    def _insert_propcol(self, name, title=None, **kwargs):
        colidx = self._table.insert_column_with_data_func(-1, title or (name[0].upper() + name[1:]),
                                                          hotwidgets.CellRendererText(**kwargs),
                                                          self._render_propcol, name)
        col = self._table.get_column(colidx-1)
        col.set_data('hotwire-propname', name)
        col.set_data('hotwire-proptype', 'any')
        col.set_resizable(True)
        return col

    def _set_search_column(self, col):
        colidx = -1
        for i,c in enumerate(self._table.get_columns()):
            if c == col:
                colidx = i
                break
        assert colidx != -1
        self.__search_enabled = True
        self._table.set_search_column(colidx)
        self._table.set_search_equal_func(col.get_data('hotwire-proptype') is unicode and self._search_proptext or self._search_propcol,
                                          col.get_data('hotwire-propname'))

    def _render_propcol(self, col, cell, model, iter, prop):
        obj = model.get_value(iter, 0)
        propval = getattr(obj, prop)
        cell.set_property('text', unicode(repr(propval)))

    def _render_proptext(self, col, cell, model, iter, prop):
        obj = model.get_value(iter, 0)
        propval = getattr(obj, prop)
        cell.set_property('text', propval)

    def _search_propcol(self, model, col, key, iter, prop):
        obj = model.get_value(iter, 0)
        propval = getattr(obj, prop)
        text = unicode(repr(propval)) 
        if text.find(key) >= 0:
            return False
        return True

    def _search_proptext(self, model, col, key, iter, prop):
        obj = model.get_value(iter, 0)
        propval = getattr(obj, prop)
        if propval.find(key) >= 0:
            return False
        return True

    def _findobj(self, obj, colidx=0):
        iter = self._model.get_iter_first()
        while iter:
            val = self._model.get_value(iter, colidx)
            if val == obj:
                return iter
            iter = self._model.iter_next(iter)

    def _signal_obj_changed(self, obj, colidx=0):
        iter = self._findobj(obj, colidx=colidx) 
        self._model.row_changed(self._model.get_path(iter), iter)

    def _render_objtext(self, col, cell, model, iter):
        obj = model.get_value(iter, 0)
        cell.set_property('text', unicode(repr(obj)))

    def append_obj(self, obj, **kwargs):
        self._model.append((obj,))

    def __onclick(self, path, col, rel_x, rel_y):
        iter = self._model.get_iter(path)
        return self._onclick_full(iter, path, col, rel_x, rel_y)

    def _onclick_full(self, iter, path, col, rel_x, rel_y):
        return self._onclick_iter(iter)

    def _onclick_iter(self, iter):
        obj = self._model.get_value(iter, 0)
        return self._onclick_obj(obj)

    def _onclick_obj(self, obj):
        return False

    def _get_menuitems(self, obj):
        return []

    # Like GtkTreeView.get_path_at_pos, but excludes headers
    def _get_path_at_pos_no_headers(self, x, y):
        potential_path = self._table.get_path_at_pos(x, y)
        if potential_path is None:
            return None
        return potential_path

    def __on_button_press(self, table, e):
        potential_path = self._get_path_at_pos_no_headers(int(e.x), int(e.y))
        if potential_path is None:
            return False
        _logger.debug("potential path is %s", potential_path)
        (path, col, rel_x, rel_y) = potential_path        
        if e.button > 1:
            iter = self._model.get_iter(path)
            menu = gtk.Menu()
            have_menuitems = False
            for menuitem in self.__get_func_menuitems(iter):
                menu.append(menuitem)
                have_menuitems = True
            for menuitem in self._get_menuitems(iter):
                menu.append(menuitem)
                have_menuitems = True
            if have_menuitems:
                menu.show_all()
                menu.popup(None, None, None, e.button, e.time)
                return True

        return False
    
    def __on_row_activated(self, tv, path, vc):
        iter = self._model.get_iter(path)        
        self._onclick_iter(iter)
        from hotwire_ui.shell import locate_current_shell
        hw = locate_current_shell(self._table)
        hw.grab_focus()        
        
class DefaultObjectsRenderer(TreeObjectsRenderer):
    pass

import hotwire_ui.renderers.file
import hotwire_ui.renderers.filestringmatch
import hotwire_ui.renderers.help
import hotwire_ui.renderers.ps
import hotwire_ui.renderers.unicode
#moddir = hotwire.ModuleDir(os.path.join(os.path.dirname(hotwire.__file__), 'renderers'))
#moddir.do_import()
