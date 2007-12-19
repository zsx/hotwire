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

class CompletionPopup(hotwidgets.TransientPopup):
    __gsignals__ = {
        "item-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }     
    def __init__(self, title, entry, window, context=None, **kwargs):
        super(CompletionPopup, self).__init__(entry, window, **kwargs)
        self.__entry = entry
        self.__window = window
        self.__maxcount = 10        
        self.__label = gtk.Label()
        self.__label.set_markup('<b>%s</b>' % (title,))
        self.get_box().pack_start(self.__label, expand=False)      
        self.__model = gtk.ListStore(gobject.TYPE_PYOBJECT)        
        self.__view = gtk.TreeView(self.__model)
        self.__selection = self.__view.get_selection()
        self.__selection.set_mode(gtk.SELECTION_SINGLE)
        self.__view.connect("row-activated", self.__on_row_activated)
        self.__view.set_headers_visible(False)
        self.get_box().add(self.__view)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          hotwidgets.CellRendererText(ellipsize=True),
                                                          self._render_item)
        self.__morelabel = gtk.Label()
        self.__morelabel.set_no_show_all(True)
        self.get_box().pack_start(self.__morelabel, expand=False)
        self.__none_label = gtk.Label()
        self.__none_label.set_no_show_all(True)
        self.__none_label.set_markup('<i>%s</i>' % (_('No matches'),))
        self.get_box().pack_start(self.__none_label, expand=False)
        
    def _get_view(self):
        return self.__view   
    
    def _get_selection(self):
        return self.__selection
    
    def set_content(self, results, uniquify=False, reverse=True):
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
        self._get_view().set_model(model)
        if results:
            self.__selection.select_iter(self.__model.iter_nth_child(None, self.__model.iter_n_children(None)-1))
            self.__none_label.hide()            
        else:
            self.__none_label.show()
        
        self.__morecount = len(results)-i                        
        if self.__morecount:
            self.__morelabel.set_text('%d more...' % (self.__morecount,))
            self.__morelabel.show_all()
        else:
            self.__morelabel.set_text('')
            self.__morelabel.hide()
            
    def iter_matches(self):
        i = self.__model.iter_n_children(None)-1
        while i >= 0:
            yield self.__model[i][0]
            i -= 1
            
    def get_display_count(self):
        return self.__model.iter_n_children(None)
            
    def __on_row_activated(self, tv, path, vc):
        _logger.debug("row activated: %s", path)
        iter = self.__model.get_iter(path)
        self.emit('histitem-selected', self.__model.get_value(iter, 0))         
    
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
        previter = self.__model.iter_nth_child(None, previdx)
        if not previter:
            return
        self.__selection.select_iter(previter)
        
    def select_prev(self):
        path = self.get_selected_path()
        if not path:
            return
        seliter = self.__model.get_iter(path)
        iternext = self.__model.iter_next(seliter)
        if not iternext:
            return
        self.__selection.select_iter(iternext)
        
    def emit_itemselected(self):
        (model, iter) = self.__selection.get_selected()
        if not iter:
            self.emit('item-selected', None)
            return
        self.emit('item-selected', model.get_value(iter, 0))

class TabHistoryPopup(CompletionPopup): 
    def __init__(self, entry, window, context=None, **kwargs):
        super(TabHistoryPopup, self).__init__(_('Tab History'), entry, window, **kwargs)
 
    def _render_item(self, col, cell, model, iter):
        histitem = model.get_value(iter, 0)
        cell.set_property('text', histitem)
        
class GlobalHistoryPopup(CompletionPopup):   
    def __init__(self, entry, window, context=None, **kwargs):
        super(GlobalHistoryPopup, self).__init__(_('History Search'), entry, window, **kwargs)
 
    def _render_item(self, col, cell, model, iter):
        histitem = model.get_value(iter, 0)
        cell.set_property('text', histitem)        

class AllCompletionPopup(CompletionPopup):
    __gsignals__ = {
        "match-selected" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
    }     
    def __init__(self, entry, window, context=None, **kwargs):
        super(AllCompletionPopup, self).__init__(_('Completions'), entry, window, **kwargs)
        self.__context = context
        self.__fs = Filesystem.getInstance()
        colidx = self._get_view().insert_column_with_data_func(0, '',
                                                               gtk.CellRendererPixbuf(),
                                                               self.__render_icon)
        
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
        self.__completion_display = AllCompletionPopup(self.__entry, self.__window, self.__context)
        self.__completion_display.connect('item-selected', self.__on_completion_selected)
        self.__completions_label = gtk.Label('No completions')
        self.__completions_label.set_alignment(0.0, 0.5)
        self.__history_label = gtk.Label('No history')
        self.__history_label.set_alignment(0.0, 0.5)
        
        self.__tab_history_display = TabHistoryPopup(self.__entry, self.__window, self.__context) 
        self.__tab_history_display.connect('item-selected', self.__on_histitem_selected)
        self.__global_history_display = GlobalHistoryPopup(self.__entry, self.__window, self.__context) 
        self.__global_history_display.connect('item-selected', self.__on_histitem_selected)
        
        self.__overview_visible = False
        self.__completion_visible = False
        self.__tab_history_visible = False
        self.__global_history_visible = False        

        self.get_box().pack_start(self.__completions_label, expand=False)
        self.get_box().pack_start(self.__history_label, expand=False)
         
    def __on_histitem_selected(self, th, histitem):
        self.emit('histitem-selected', histitem)
         
    def __on_completion_selected(self, ac, compl):
        self.emit('completion-selected', compl)

    def invalidate(self):
        self.__completions_label.set_text(' ')
        self.__token = None
        self.__completer = None
        self.__current_completion = None
        self.__pending_completion_load = False
        self.hide_all()

    def hide_all(self):
        self.__completion_display.hide()
        self.__completion_visible = False
        self.__tab_history_display.hide()
        self.__tab_history_visible = False
        self.__global_history_display.hide()
        self.__global_history_visible = False
        super(CompletionStatusDisplay, self).hide()
        self.__overview_visible = False

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
            self.__completion_display.set_content(self.__current_completion.results)
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
        if self.__pending_completion_load:
            self.__current_completion = results            
            self.emit('completions-loaded')
            self.__pending_completion_load = False
        else:
            if self.__current_completion.common_prefix:
                pfx = gobject.markup_escape_text(self.__current_completion.common_prefix)
                self.__completions_label.set_markup(_('Completion <b>[TAB]</b>: %s <b>(%d more)</b>') 
                                                    % (pfx,len(self.__current_completion.results)))
            elif self.__current_completion.results:
                first = self.__current_completion.results[0]
                # FIXME kill matchbase replace with handling of object
                if first.matchbase:
                    firsttext = gobject.markup_escape_text(first.matchbase)
                else:
                    firsttext = gobject.markup_escape_text(first.suffix)
                self.__completions_label.set_markup(_('Completion <b>[TAB]</b>: %s <b>(%d more)</b>') 
                                                    % (firsttext,len(self.__current_completion.results)-1))
            else:
                self.__completions_label.set_markup(_('Completion: (no matches)'))
            self.show()
            self.queue_reposition()

    def _set_size_request(self):            
        (ref_x, ref_y, ref_w, ref_h, bits) = self.__entry.get_parent_window().get_geometry()
        _logger.debug("setting size request width to %d*0.75", ref_w)
        self.set_size_request((int(ref_w*0.75)), -1)
        
    def set_history_search(self, histsearch):           
        histitems = list(self.__context.history.search_commands(histsearch, distinct=True))
        self.__global_history_display.set_content(histitems, uniquify=True)        
        if histitems:
            histmatch = gobject.markup_escape_text(self.__global_history_display.iter_matches().__iter__().next())
            self.__history_label.set_markup(_('History items <b>[Ctrl-r]</b>: <span font_family="Monospace">%s</span> <b>%d more</b>') 
                                            % (histmatch, self.__global_history_display.get_display_count()-1))
        else:
            self.__history_label.set_text(_('History items: (no matches)'))
            
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
