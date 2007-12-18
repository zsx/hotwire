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
        self.get_box().pack_start(self.__completions_label, expand=False)
        self.get_box().pack_start(self.__history_label, expand=False)
         
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
        self.hide()        
        if self.__current_completion is not None:
            self.__completion_display.set_results(self.__current_completion)
            self.__completion_display.show_all()
            self.__completion_display.reposition()
            self.__completion_display.queue_reposition()
            return self.__current_completion
        self.__pending_completion_load = True
        return None
        
    def completion_is_singleton(self):
        return False
        
    def set_history_search(self, histsearch):
        pass
        
    def __completions_result(self, completer, text, results):
        if not (text == self.__token and completer == self.__completer):
            _logger.debug("stale completion result")
            return
        self.__current_completion = results
        self.__completions_label.set_text('Completions: %d' % (len(results.results),))
        if self.__pending_completion_load:
            self.emit('completions-loaded')
            self.__pending_completion_load = False           
        else:
            self.show()
            self.queue_reposition()

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
