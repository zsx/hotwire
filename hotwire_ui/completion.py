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

import os, sys, re, logging

import gtk, gobject, pango

import hotwire_ui.widgets as hotwidgets
from hotwire.completion import Completion, CompletionSystem, CompletionResults
from hotwire.util import markup_for_match
from hotwire_ui.pixbufcache import PixbufCache
from hotwire.state import History
from hotwire.sysdep.fs import File, Filesystem
from hotwire.sysdep.proc import Process

_logger = logging.getLogger("hotwire.ui.Completion")

class TabHistoryDisplay(hotwidgets.TransientPopup):
    __gsignals__ = {
        "histitem-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }     
    def __init__(self, entry, window, context=None, **kwargs):
        super(TabHistoryDisplay, self).__init__(entry, window, **kwargs)
        self.__entry = entry
        self.__window = window        
        self.__model = gtk.ListStore(gobject.TYPE_PYOBJECT)        
        self.__view = gtk.TreeView(self.__model)
        self.__selection = self.__view.get_selection()
        self.__selection.set_mode(gtk.SELECTION_SINGLE)
        self.__selection.connect('changed', self.__on_selection_changed)
        self.__selection_suppress = False
        self.__view.connect("row-activated", self.__on_row_activated)
        self.__view.set_headers_visible(False)
        self.get_box().add(self.__view)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          hotwidgets.CellRendererText(ellipsize=True),
                                                          self.__render_histitem)             

    def set_history(self, histitems):
        self.__selection_suppress = True        
        self.__model.clear()        
        for i,histitem in enumerate(reversed(histitems)):
            iter = self.__model.append([histitem])
        self.__selection_suppress = False            
        if histitems:
            self.__selection.select_iter(self.__model.iter_nth_child(None, self.__model.iter_n_children(None)-1))
            
    def __on_row_activated(self, tv, path, vc):
        _logger.debug("row activated: %s", path)
        iter = self.__model.get_iter(path)        
        self.__view.get_selection().select_iter(iter)
    
    def __on_selection_changed(self, sel):
        if self.__selection_suppress:
            return
        (model, iter) = self.__selection.get_selected()
        if not iter:
            return        
        self.emit('histitem-selected', self.__model.get_value(iter, 0))        
            
    def _set_size_request(self):            
        (ref_x, ref_y, ref_w, ref_h, bits) = self.__entry.get_parent_window().get_geometry()
        _logger.debug("setting size request width to %d*0.75", ref_w)
        self.set_size_request((int(ref_w*0.75)), -1)
        
    def __render_histitem(self, col, cell, model, iter):
        histitem = model.get_value(iter, 0)
        cell.set_property('text', histitem)

    def get_selected_path(self):
        (model, iter) = self.__selection.get_selected()
        return iter and model.get_path(iter)
        
    def select_next(self):
        path = self.get_selected_path()
        print "next from %s" % (path,)
        previdx = path[-1]-1
        if previdx < 0:
            return
        previter = self.__model.iter_nth_child(None, previdx)
        print previter
        if not previter:
            print "fail"
            return
        self.__selection.select_iter(previter)
        
    def select_prev(self):
        path = self.get_selected_path()
        print "prev from %s" % (path,)
        seliter = self.__model.get_iter(path)
        iternext = self.__model.iter_next(seliter)
        print iternext
        if not iternext:
            print "fail"
            return
        self.__selection.select_iter(iternext)

class CompletionDisplay(hotwidgets.TransientPopup):
    __gsignals__ = {
        "match-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
    }     
    def __init__(self, entry, window, context=None, **kwargs):
        super(CompletionDisplay, self).__init__(entry, window, **kwargs)
        self.__context = context
        self.__fs = Filesystem.getInstance()
        self.__maxcount = 10
        self.__model = gtk.ListStore(gobject.TYPE_PYOBJECT)
        self.__view = gtk.TreeView(self.__model)
        self.__view.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.__view.connect("row-activated", self.__on_row_activated)
        self.__view.set_headers_visible(False)
        self.get_box().add(self.__view)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          gtk.CellRendererPixbuf(),
                                                          self.__render_icon)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          hotwidgets.CellRendererText(),
                                                          self.__render_match)
        col = self.__view.get_column(colidx-1)
        col.set_expand(True)
        self.__morelabel = gtk.Label()
        self.get_box().pack_start(self.__morelabel, expand=False)
        
    def set_results(self, results):
        model = gtk.ListStore(gobject.TYPE_PYOBJECT)
        overmax = False
        for i,completion in enumerate(results.results):
            if i >= self.__maxcount:
                overmax = True
                break
            iter = model.append([completion])
        self.__model = model
        self.__view.set_model(model)
        if overmax:
            self.__morelabel.set_text('%d more...' % (len(results.results)-self.__maxcount,))
            self.__morelabel.show_all()
        else:
            self.__morelabel.set_text('')
            self.__morelabel.hide()
        
    def __get_icon_func_for_klass(self, klass):
        if isinstance(klass, File):
            return self.__fs.get_file_icon_name
        elif isinstance(klass, Process):
            return lambda x: 'gtk-execute'
        else:
            return None

    def __render_icon(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        icon_name = None
        if compl.target:
            ifunc = self.__get_icon_func_for_klass(compl.target)
            if ifunc:
                icon_name = ifunc(compl.target)
        if icon_name:
            if icon_name.startswith(os.sep):
                pixbuf = PixbufCache.getInstance().get(icon_name)
                cell.set_property('pixbuf', pixbuf)
            else:
                cell.set_property('icon-name', icon_name)
        else:
            cell.set_property('icon-name', None)
            
    def __findobj(self, obj):
        iter = self.__model.get_iter_first()
        while iter:
            val = self.__model.get_value(iter, 0)
            if val is obj:
                return iter
            iter = self.__model.iter_next(iter)
            
    def __on_row_activated(self, tv, path, vc):
        _logger.debug("row activated: %s", path)
        iter = self.__model.get_iter(path)        
        self.__view.get_selection().select_iter(iter)
        self.emit('match-selected')

    def __render_match(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        if compl.matchbase:
            cell.set_property('text', compl.matchbase)
        else:
            cell.set_property('text', compl.suffix)
 
class CompletionStatusDisplay(hotwidgets.TransientPopup):
    __gsignals__ = {
        "histitem-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),                    
        "completion-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "completions-loaded" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),        
    }    
    def __init__(self, entry, window, context=None, tabhistory=[], **kwargs):
        super(CompletionStatusDisplay, self).__init__(entry, window, **kwargs)
        self.__entry = entry
        self.__window = window
        self.__context = context
        self.__tabhistory = tabhistory
        self.__token = None
        self.__completer = None
        self.__complsys = CompletionSystem()
        self.__current_completion = None
        self.__pending_completion_load = False
        self.__completion_display = CompletionDisplay(self.__entry, self.__window, self.__context)
        self.__completions_label = gtk.Label('No completions')
        self.__history_label = gtk.Label('No history')
        
        self.__tab_history_display = TabHistoryDisplay(self.__entry, self.__window, self.__context) 
        self.__tab_history_display.connect('histitem-selected', self.__on_histitem_selected)

        self.get_box().pack_start(self.__completions_label, expand=False)
        self.get_box().pack_start(self.__history_label, expand=False)
         
    def __on_histitem_selected(self, th, histitem):
        self.emit('histitem-selected', histitem)
         
    def __on_completion_match_selected(self, tm):
        self.emit('completion-selected')

    def invalidate(self):
        self.__completions_label.set_text(' ')
        self.__token = None
        self.__completer = None
        self.__current_completion = None
        self.__pending_completion_load = False
        self.__completion_display.hide()

    def hide_all(self):
        self.__completion_display.hide()
        self.__tab_history_display.hide()
        super(CompletionStatusDisplay, self).hide()

    def set_completion(self, completer, text, context):
        if text == self.__token and completer == self.__completer:
            return
        _logger.debug("new completion: %s", text)
        self.invalidate()
        self.__token = text
        self.__completer = completer
        self.__completions_label.set_text('Loading...')
        self.__complsys.async_complete(completer, text, context.get_cwd(), self.__completions_result)
        
    def completion_request(self):      
        if self.__current_completion is not None:
            self.__completion_display.set_results(self.__current_completion)
            self.hide_all()
            self.__completion_display.show()
            self.__completion_display.reposition()
            self.__completion_display.queue_reposition()
            return self.__current_completion
        self.hide_all()
        self.__pending_completion_load = True
        return None
        
    def __completions_result(self, completer, text, results):
        if not (text == self.__token and completer == self.__completer):
            _logger.debug("stale completion result")
            return
        self.__current_completion = results
        if self.__pending_completion_load:
            self.__current_completion = results            
            self.emit('completions-loaded')
            self.__pending_completion_load = False
        else:        
            self.__completions_label.set_text('Completions: %d' % (len(results.results),))
            self.show()
            self.queue_reposition()

    def _set_size_request(self):            
        (ref_x, ref_y, ref_w, ref_h, bits) = self.__entry.get_parent_window().get_geometry()
        _logger.debug("setting size request width to %d*0.75", ref_w)
        self.set_size_request((int(ref_w*0.75)), -1)
        
    def set_history_search(self, histsearch, now=False):
        if now:
            self.__tab_history_display.set_history(self.__tabhistory)
            self.__tab_history_display.reposition()
            self.__tab_history_display.queue_reposition()
            self.__tab_history_display.show()
            
    def select_history_next(self):
        self.__tab_history_display.select_next()
        
    def select_history_prev(self):
        self.__tab_history_display.select_prev()
            

#    def set_history_search(self, search, now=False):
#        self.__search = search
#        self.__selected = None
#        self.__saved_input = None
#        _logger.debug("new history search: %s", search)
#        if not now:
#            self.history.set_compact(not self.__search)
#            # Be sure we suppress one-character searches here; they aren't going
#            # to be useful.
#            if search and (len(search) > 1) and self.__idle_history_search_id == 0:
#                _logger.debug("queuing idle history search for '%s'", search)
#                self.__idle_history_search_id = gobject.timeout_add(300, self.__idle_do_history_search)
#            elif not search:
#                if self.__idle_history_search_id > 0:
#                    gobject.source_remove(self.__idle_history_search_id)
#                    self.__idle_history_search_id = 0
#                self.history.set_generator(None)
#                self.__check_hide()
#        else:
#            if self.__idle_history_search_id > 0:
#                gobject.source_remove(self.__idle_history_search_id)
#            self.__idle_do_history_search()
#            self.tabcompletion.hide()
#            self.history.expand()
#            self.__queue_reposition()
#
#    def __idle_do_history_search(self):
#        self.__idle_history_search_id = 0
#        if self.__search:
#            histsrc = self.__context.history.search_commands(self.__search)
#        else:
#            histsrc = self.__tabhistory
#        self.history.set_generator(self.__generate_history(histsrc))
#        visible = self.__check_hide()
#        if visible:
#            self.show()
#            self.__queue_reposition()
#
#    def __generate_history(self, src):
#        for histitem in src:
#            if self.__search:
#                idx = histitem.find(self.__search)
#                if idx < 0:
#                    continue
#                compl = Completion(histitem, idx, len(self.__search))
#                yield compl
#            else:
#                yield Completion(histitem, 0, 0)
