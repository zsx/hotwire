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
from hotwire.builtin import Builtin
from hotwire.cmdalias import Alias
from hotwire.sysdep.fs import File, Filesystem
from hotwire.sysdep.proc import Process

_logger = logging.getLogger("hotwire.ui.Completion")

class MatchView(gtk.VBox):
    def __init__(self, title, maxcount=10, keybinding=None):
        super(MatchView, self).__init__()
        self.__maxcount = maxcount
        headerhbox = gtk.HBox()
        self.__label = gtk.Label()
        self.__label.set_alignment(0.0, 0.5)
        headerhbox.add(self.__label)
        if keybinding:
            self.__keybinding_label = gtk.Label()
            self.__keybinding_label.set_markup(_('Key: <tt>%s</tt>') % (keybinding,))
            self.__keybinding_label.set_alignment(1.0, 0.5)
            headerhbox.add(self.__keybinding_label)
        self.__title = title
        self.__morecount = -1
        self.__keybinding = keybinding
        self.set_more_count(self.__morecount)
        self.pack_start(headerhbox, expand=False)      
        self.__model = gtk.ListStore(gobject.TYPE_PYOBJECT)        
        self.__view = gtk.TreeView(self.__model)
        self.__selection = self.__view.get_selection()
        self.__selection.set_mode(gtk.SELECTION_SINGLE)
        self.__view.set_headers_visible(False)
        self.add(self.__view)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          hotwidgets.CellRendererText(ellipsize=True),
                                                          self._render_item)
        self.__none_label = gtk.Label()
        self.__none_label.set_alignment(0.0, 0.5)
        self.__none_label.set_no_show_all(True)
        self.__none_label.set_markup('<i>%s</i>' % (_('(No matches)'),))
        self.pack_start(self.__none_label, expand=False)         
    
    def get_view(self):
        return self.__view 
    
    def get_model(self):
        return self.__model

    def get_selection(self):
        return self.__selection
    
    def set_more_count(self, morecount):
        self.__morecount = morecount
        if morecount < 0:
            self.__label.set_text(self.__title)
        else:
            self.__label.set_markup('%s - <b>%d</b> total' % \
                                    (gobject.markup_escape_text(self.__title),
                                     self.__morecount+1))
    
    def set_content(self, results, uniquify=False, reverse=True, do_select=True):
        model = gtk.ListStore(gobject.TYPE_PYOBJECT)
        overmax = False
        uniqueresults = set()
        i = 0
        for completion in results:
            if i >= self.__maxcount:
                overmax = True
                break
            if uniquify and completion in uniqueresults:
                continue
            uniqueresults.add(completion)
            i += 1
            if reverse:
                iter = model.prepend([completion])
            else:
                iter = model.append([completion])
        self.__model = model
        self.__view.set_model(model)
        if results and do_select:
            self.__selection.select_iter(self.__model.iter_nth_child(None, self.__model.iter_n_children(None)-1))
        if results:
            self.__none_label.hide()
        else:
            self.__none_label.show()            
            
    def iter_matches(self):
        i = self.__model.iter_n_children(None)-1
        while i >= 0:
            yield self.__model[i][0]
            i -= 1
    
    def get_display_count(self):        
        return self.__model.iter_n_children(None)             

class MatchPopup(hotwidgets.TransientPopup):
    __gsignals__ = {
        "item-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }     
    def __init__(self, title, viewklass, entry, window, context=None, **kwargs):
        super(MatchPopup, self).__init__(entry, window, **kwargs)
        self.__entry = entry
        self.__window = window
        self.__maxcount = 10
        
        self.__view = viewklass(title)
        self.__selection = self.__view.get_selection()
        self.get_box().pack_start(self.__view, expand=True)
        self.__miniview = viewklass(title, maxcount=1)
        self.__view.get_view().connect("row-activated", self.__on_row_activated)        
        self.__morelabel = gtk.Label()
        self.__morelabel.set_no_show_all(True)
        self.get_box().pack_start(self.__morelabel, expand=False)
        self.__none_label = gtk.Label()
        self.__none_label.set_alignment(0.0, 0.5)
        self.__none_label.set_no_show_all(True)
        self.__none_label.set_markup('<i>%s</i>' % (_('(No matches)'),))
        self.get_box().pack_start(self.__none_label, expand=False)               
        
    def _get_view(self):
        return self.__view
    
    def get_miniview(self):
        return self.__miniview

    def set_content(self, results, **kwargs):
        self.__view.set_content(results, **kwargs)
        self.__miniview.set_content(results, do_select=False, **kwargs)
          
        self.__morecount = len(results)-self.__view.get_display_count()                        
        if self.__morecount:
            self.__morelabel.set_text(_('%d more...') % (self.__morecount,))
            self.__morelabel.show_all()
        else:
            self.__morelabel.set_text('')
            self.__morelabel.hide()
        
        self.__miniview.set_more_count(self.__view.get_display_count()-1)
            
        if results:
            self.__none_label.hide()
        else:
            self.__none_label.show()
        
    def set_matchtext(self, matchtext):
        self.__view.set_matchtext(matchtext)
        self.__miniview.set_matchtext(matchtext)
            
    def iter_matches(self, *args, **kwargs):
        for x in self.__view.iter_matches(*args, **kwargs):
            yield x
            
    def get_display_count(self):
        return self.__view.get_display_count()       
    
    def _set_size_request(self):            
        (ref_x, ref_y, ref_w, ref_h, bits) = self.__entry.get_parent_window().get_geometry()
        _logger.debug("setting size request width to %d*0.75", ref_w)
        self.set_size_request((int(ref_w*0.75)), -1)

    def get_selected_path(self):
        (model, iter) = self.__selection.get_selected()
        return iter and model.get_path(iter)
        
    def select_next(self):
        path = self.get_selected_path()
        if not path:
            return
        previdx = path[-1]-1
        if previdx < 0:
            return
        model = self.__view.get_model()        
        previter = model.iter_nth_child(None, previdx)
        if not previter:
            return
        self.__selection.select_iter(previter)
        
    def select_prev(self):
        path = self.get_selected_path()
        if not path:
            return
        model = self.__view.get_model()        
        seliter = model.get_iter(path)
        iternext = model.iter_next(seliter)
        if not iternext:
            return
        self.__selection.select_iter(iternext)
        
    def emit_itemselected(self):
        (model, iter) = self.__selection.get_selected()
        if not iter:
            self.emit('item-selected', None)
            return
        self.emit('item-selected', model.get_value(iter, 0))
        
    def __on_row_activated(self, tv, path, vc):
        _logger.debug("row activated: %s", path)
        model = self.__view.get_model()
        iter = model.get_iter(path)
        self.emit('item-selected', model().get_value(iter, 0))           

class MatchingHistoryView(MatchView):
    def __init__(self, *args, **kwargs):
        super(MatchingHistoryView, self).__init__(*args, **kwargs)
        self.__matchtext = None
 
    def set_matchtext(self, text):
        self.__matchtext = text
        self.get_model().foreach(gtk.TreeModel.row_changed)
 
    def _render_item(self, col, cell, model, iter):
        histitem = model.get_value(iter, 0)
        if self.__matchtext:
            idx = histitem.find(self.__matchtext)
            if idx >= 0:
                markup = markup_for_match(histitem, idx, idx+len(self.__matchtext))
                cell.set_property('markup', markup)
                return
        cell.set_property('text', histitem)

class TabCompletionView(MatchView):
    def __init__(self, *args, **kwargs):
        super(TabCompletionView, self).__init__(*args, **kwargs)
        self.__fs = Filesystem.getInstance()
        colidx = self.get_view().insert_column_with_data_func(0, '',
                                                              gtk.CellRendererPixbuf(),
                                                              self.__render_icon)
        
    def __get_icon_func_for_klass(self, klass):
        if isinstance(klass, File):
            return self.__fs.get_file_icon_name
        elif isinstance(klass, Builtin):
            return lambda x: 'hotwire'
        elif isinstance(klass, Alias):
            return lambda x: 'gtk-convert'           
        elif isinstance(klass, Process):
            return lambda x: 'gtk-execute'
        else:
            return None

    def __render_icon(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        icon_name = compl.icon
        if (not icon_name) and compl.target:
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
        model  = self.get_model()
        iter = model.get_iter_first()
        while iter:
            val = model.get_value(iter, 0)
            if val is obj:
                return iter
            iter = model.iter_next(iter)

    def _render_item(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        if compl.matchbase:
            cell.set_property('text', compl.matchbase)
        else:
            cell.set_property('text', compl.suffix)

class CompletionStatusDisplay(hotwidgets.TransientPopup):
    __gsignals__ = {
        "histitem-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),                    
        "completion-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
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
        self.__completion_display = MatchPopup(_('Completions (%s)') % ('TAB',),
                                               TabCompletionView,                                                
                                               self.__entry, self.__window, self.__context)
        self.__completion_display.connect('item-selected', self.__on_completion_selected)
        self.__tab_history_display = MatchPopup(_('Tab History'), 
                                                MatchingHistoryView,                                                 
                                                self.__entry, self.__window, self.__context) 
        self.__tab_history_display.connect('item-selected', self.__on_histitem_selected)
        self.__global_history_display = MatchPopup(_('Global History Search (%s)') % ('Ctrl-R',), 
                                                   MatchingHistoryView,
                                                   self.__entry, self.__window, self.__context) 
        self.__global_history_display.connect('item-selected', self.__on_histitem_selected)
        
        self.__overview_visible = False
        self.__completion_visible = False
        self.__tab_history_visible = False
        self.__global_history_visible = False        

        self.get_box().pack_start(self.__completion_display.get_miniview(), expand=True)
        self.get_box().pack_start(gtk.VSeparator(), expand=False)
        self.get_box().pack_start(self.__global_history_display.get_miniview(), expand=True)
         
    def __on_histitem_selected(self, th, histitem):
        self.emit('histitem-selected', histitem)
         
    def __on_completion_selected(self, ac, compl):
        self.emit('completion-selected', compl)

    def invalidate(self):
        self.__token = None
        self.__completer = None
        self.__current_completion = None
        self.__pending_completion_load = False
        self.hide_all()

    def hide_all(self):
        if self.__completion_visible:
            self.__completion_display.hide()
        self.__completion_visible = False
        if self.__tab_history_visible:
            self.__tab_history_display.hide()
        self.__tab_history_visible = False
        if self.__global_history_visible:
            self.__global_history_display.hide()
        self.__global_history_visible = False
        if self.__overview_visible:
            super(CompletionStatusDisplay, self).hide()
        self.__overview_visible = False

    def set_completion(self, completer, text, context):
        if text == self.__token and completer == self.__completer:
            return
        _logger.debug("new completion: %s", text)
        self.invalidate()
        self.__token = text
        self.__completer = completer
        self.__complsys.async_complete(completer, text, context.get_cwd(), self.__completions_result)
        
    def completion_request(self):      
        if self.__current_completion is not None:
            if not self.__completion_visible:
                self.hide_all()
                self.__completion_visible = True
                self.__completion_display.show()
            self.__completion_display.reposition()
            self.__completion_display.queue_reposition()
            return self.__current_completion
        self.hide_all()
        self.__pending_completion_load = True
        return None
    
    def show(self):
        self.__overview_visible = True
        super(CompletionStatusDisplay, self).show()
        self.reposition()
        self.queue_reposition()
        
    def hide(self):
        self.__overview_visible = False
        super(CompletionStatusDisplay, self).hide()
        
    def __completions_result(self, completer, text, results):
        if not (text == self.__token and completer == self.__completer):
            _logger.debug("stale completion result")
            return
        self.__current_completion = results
        self.__completion_display.set_content(self.__current_completion.results)        
        if self.__pending_completion_load:
            self.__current_completion = results            
            self.emit('completions-loaded')
            self.__pending_completion_load = False
        else:
            self.show()
            self.queue_reposition()

    def _set_size_request(self):            
        (ref_x, ref_y, ref_w, ref_h, bits) = self.__entry.get_parent_window().get_geometry()
        _logger.debug("setting size request width to %d*0.75", ref_w)
        self.set_size_request((int(ref_w*0.75)), -1)
        
    def set_history_search(self, histsearch):           
        histitems = list(self.__context.history.search_commands(histsearch, distinct=True))
        self.__global_history_display.set_content(histitems, uniquify=True)
        self.__global_history_display.set_matchtext(histsearch)
            
    def popup_tab_history(self):
        if self.__tab_history_visible:
            return
        self.hide()
        self.__tab_history_display.set_content(self.__tabhistory, uniquify=False)         
        self.__tab_history_display.reposition()
        self.__tab_history_display.queue_reposition()
        self.__tab_history_visible = True
        self.__tab_history_display.show()
        
    def popup_global_history(self):
        if self.__global_history_visible:
            return
        self.hide()
        self.__global_history_display.reposition()
        self.__global_history_display.queue_reposition()
        self.__global_history_visible = True
        self.__global_history_display.show()            

    def get_state(self):
        if self.__tab_history_visible:
            return 'tabhistory'
        elif self.__global_history_visible:
            return 'globalhistory'
        elif self.__completion_visible:
            return 'completions'
        return None

    def select_next(self):
        if self.__tab_history_visible:
            self.__tab_history_display.select_next()
            return True
        elif self.__global_history_visible:
            self.__global_history_display.select_next()
            return True
        elif self.__completion_visible:
            self.__completion_display.select_next()
            return True
        return False
        
    def select_prev(self):
        if self.__tab_history_visible:
            self.__tab_history_display.select_prev()
            return True
        elif self.__global_history_visible:
            self.__global_history_display.select_prev()
            return True
        elif self.__completion_visible:
            self.__completion_display.select_prev()
            return True
        return False

    def activate_selected(self):
        if self.__tab_history_visible:
            self.__tab_history_display.emit_itemselected()
            return True
        elif self.__global_history_visible:
            self.__global_history_display.emit_itemselected()
            return True
        elif self.__completion_visible:
            self.__completion_display.emit_itemselected()
            return True
        return False
