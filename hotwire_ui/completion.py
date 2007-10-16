import os, sys, re, logging

import gtk, gobject, pango

import hotwire_ui.widgets as hotwidgets
from hotwire.completion import Completion
from hotwire.util import markup_for_match
from hotwire_ui.pixbufcache import PixbufCache
from hotwire.state import History

_logger = logging.getLogger("hotwire.ui.Completion")

class GeneratorModelWindow(object):
    def __init__(self, generator, model, selection, dispsize, uniquify=True,
                 pullcb=None, init_dispsize=0):
        super(GeneratorModelWindow, self).__init__()
        self.model = model
        self.generator = generator
        self.selection = selection
        self.dispsize = dispsize
        self.pullcb = pullcb
        self.__prevstack = []
        self.__nextstack = []
        self.__unique_hits = {}
        self.__expanded = False
        while True:
            try:
                self.__nextstack.append(self.__generate_next())
            except StopIteration, e:
                break
        for i in xrange(init_dispsize):
            if not self._shift(): 
                break
        self.__first_is_next = True

    def prev_itemcount(self):
        return len(self.__prevstack)

    def itemcount(self):
        return self.prev_itemcount() + self.model.iter_n_children(None) + self.next_itemcount()

    def next_itemcount(self):
        return len(self.__nextstack)        

    def __ret_selected(self):
        (model, iter) = self.selection.get_selected()
        if not iter:
            return None
        return self.model.get_value(iter, 0)

    def get_selected_path(self):
        (model, iter) = self.selection.get_selected()
        return iter and model.get_path(iter)

    def expand(self):
        if self.__expanded:
            return
        self.__expanded = True
        for i in xrange(self.dispsize-1):
            if not self._shift():
                return

    def get_expanded(self):
        return self.__expanded

    def get_common_prefix(self):
        return self.__common_prefix

    def next(self):
        selpath = self.get_selected_path()
        if not selpath:
            iter_first = self.model.get_iter_first()
            if not iter_first:
                return None
            self.selection.select_iter(iter_first)
            self.__first_is_next = False
        elif selpath == self.__path_last():
            return None
        elif selpath[-1] >= self.dispsize/2:
            selidx = selpath[-1]
            if not self._shift():
                self.selection.select_path(selidx+1)
            else:
                self.selection.select_path(selidx)
        elif not self.__first_is_next:
            seliter = self.model.get_iter(selpath)
            iternext = self.model.iter_next(seliter)
            self.selection.select_iter(iternext)
        elif self.__first_is_next:
            self.__first_is_next = False
        return self.__ret_selected()

    def prev(self):
        selpath = self.get_selected_path()
        if not selpath:
            return None
        iter_first = self.model.get_iter_first() 
        if not iter_first:
            return None
        if selpath == self.model.get_path(iter_first):
            if not self._unshift():
                return None
            firstiter = self.model.get_iter_first()
            self.selection.select_iter(firstiter)
        else:
            selidx = selpath[-1]
            self.selection.select_iter(self.model.iter_nth_child(None, selidx-1))
        return self.__ret_selected()

    def __generate_next(self):
        while True:
            nextvals = self.generator.next()
            item = nextvals.mstr
            if not self.__unique_hits.has_key(item):
                self.__unique_hits[item] = True
                self.pullcb(nextvals)
                return nextvals

    def _shift(self):
        if self.__nextstack:
            nextvals = self.__nextstack.pop(0)
        else:
            return False
        n = self.model.iter_n_children(None)
        if n >= self.dispsize:
            iter = self.model.get_iter_first()
            vals = self.model.get(iter, 0)
            self.__prevstack.append(vals)
            self.model.remove(iter)
        self.model.append([nextvals])
        return True

    def _unshift(self):
        if len(self.__prevstack) == 0:
            return False
        prev = self.__prevstack.pop() 
        n = self.model.iter_n_children(None)
        if n >= self.dispsize:
            iter = self.__iter_last()
            vals = self.model.get(iter, 0)
            self.__nextstack.append(vals)
            self.model.remove(iter)
        self.model.insert(0, prev)
        return True

    def __iter_last(self):
        iter = self.model.get_iter_first()
        while iter:
            nextiter = self.model.iter_next(iter)
            if not nextiter:
                return iter
            iter = nextiter
        return iter

    def __path_last(self):
        iter = self.__iter_last()
        if not iter:
            return None
        return self.model.get_path(iter)

    def has_next(self):
        selpath = self.get_selected_path()
        lastpath = self.__path_last() 
        return (lastpath is not None) and selpath != lastpath

class TextMatchDisplay(gtk.VBox):
    def __init__(self, title='', dispcount=5, context=None,
                 extended_title=None, init_dispsize=0):
        super(TextMatchDisplay, self).__init__()
        self.__context = context
        self.__dispcount = dispcount
        self.__init_dispsize = init_dispsize
        self.__title = gtk.Label()
        self.__title_markup = title
        self.__extended_title = extended_title
        self.__view = gtk.TreeView()
        self.__view.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.__view.set_headers_visible(False)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          gtk.CellRendererPixbuf(),
                                                          self.__render_icon)
        colidx = self.__view.insert_column_with_data_func(-1, '',
                                                          hotwidgets.CellRendererText(ellipsize=True),
                                                          self.__render_match)
        col = self.__view.get_column(colidx-1)
        col.set_expand(True)
        self.__view.insert_column_with_data_func(-1, '',
                                                 hotwidgets.CellRendererText(),
                                                 self.__render_matchtype)
        self.pack_start(self.__title, expand=False)
        self.__prevhits = gtk.Label()
        self.__prevhits.set_no_show_all(True)
        self.pack_start(self.__prevhits, expand=False)
        self.pack_start(self.__view, expand=True)
        self.__nexthits = gtk.Label()
        self.__nexthits.set_no_show_all(True)
        self.pack_start(self.__nexthits, expand=False)
        self.__gen_window = None
        self.__saved_input = None

    def __render_icon(self, col, cell, model, iter):
        obj = model.get_value(iter, 0)
        icon_name = obj.get_icon(self.__context)
        if icon_name:
            if icon_name.startswith(os.sep):
                pixbuf = PixbufCache.getInstance().get(icon_name)
                cell.set_property('pixbuf', pixbuf)
            else:
                cell.set_property('icon-name', icon_name)
        else:
            cell.set_property('icon-name', None)

    def set_compact(self, compacted):
        if compacted:
            self.__view.hide()
        else:
            self.__view.show()

    def __findobj(self, obj):
        iter = self.__model.get_iter_first()
        while iter:
            val = self.__model.get_value(iter, 0)
            if val is obj:
                return iter
            iter = self.__model.iter_next(iter)

    def __on_icon_changed(self, compl):
        if not self.__model:
            return
        iter = self.__findobj(compl)
        if not iter:
            _logger.debug("no iter found for compl %s", compl)
            return
        self.__model.row_changed(self.__model.get_path(iter), iter)

    def __set_icon_cb(self, completion):
        completion.set_icon_cb(lambda compl: self.__on_icon_changed(compl))

    def set_generator(self, more):
        self.__saved_input = None
        self.__model = gtk.ListStore(gobject.TYPE_PYOBJECT)
        self.__view.set_model(self.__model)
        if more:
            self.__gen_window = GeneratorModelWindow(more.__iter__(), self.__model,
                                                     self.__view.get_selection(),
                                                     self.__dispcount,
                                                     pullcb=self.__set_icon_cb,
                                                     init_dispsize=self.__init_dispsize)
        else:
            self.__gen_window = None
        self.__sync_display()

    def expand(self):
        if self.__gen_window:
            self.__gen_window.expand()

    def get_expanded(self):
        if self.__gen_window:
            return self.__gen_window.get_expanded()
        return False

    def itemcount(self):
        if self.__gen_window:
            return self.__gen_window.itemcount()
        return 0

    def empty(self):
        return self.itemcount() == 0

    def __render_match(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        (mstr, start, mlen) = compl.get_matchdata() 
        markup = markup_for_match(mstr, start, start+mlen, compl.matchtarget) 
        cell.set_property('markup', markup)

    def __render_matchtype(self, col, cell, model, iter):
        compl = model.get_value(iter, 0)
        if compl.typename:
            cell.set_property('text', compl.typename)
        else:
            cell.set_property('text', '')

    def __item_from_match(self, item):
        if not (item is None):
            return item.get_matchdata()[0]
        return None

    def __sync_display(self):
        if not self.__gen_window:
            return
        path = self.__gen_window.get_selected_path()
        if path:
            self.__view.get_selection().select_path(path)
        else:
            self.__view.get_selection().unselect_all()
        totalhits = self.__gen_window.itemcount()
        hit_text = str(totalhits)
        if self.__extended_title:
            self.__title.set_markup(self.__title_markup % (hit_text, path and self.__extended_title or ''))
        else:
            self.__title.set_markup(self.__title_markup % (hit_text,))
        def fmt_hitcount(count, widget):
            if count == 0:
                widget.hide()
            else:
                widget.show()
                widget.set_markup('<small>%d more</small>' % (count,))
        fmt_hitcount(self.__gen_window.prev_itemcount(), self.__prevhits)
        fmt_hitcount(self.__gen_window.next_itemcount(), self.__nexthits)

    def select_next(self, saved_input=None):
        self.expand()
        if not self.__saved_input:
            self.__saved_input = saved_input
        if not self.__gen_window:
            return None
        result = self.__item_from_match(self.__gen_window.next())
        _logger.debug("selected next item: %s", result)
        self.__sync_display()
        return result

    def select_prev(self):
        self.expand()
        if not self.__gen_window:
            if self.__saved_input:
                result = self.__saved_input
                self.__saved_input = None
                return result
            return None
        result = self.__item_from_match(self.__gen_window.prev())
        _logger.debug("selected prev item: %s", result)
        self.__sync_display()
        return result

class PopupDisplay(hotwidgets.TransientPopup):
    def __init__(self, entry, window, context=None, tabhistory=[], **kwargs):
        super(PopupDisplay, self).__init__(entry, window, **kwargs)
        self.__context = context
        self.__tabhistory = tabhistory
        self.__tabprefix = None
        self.tabcompletion = TextMatchDisplay(title=u'<b>Completion</b> - %s matches <b>(</b><tt>TAB</tt> next%s<b>)</b>',
                                              context=context,
                                              extended_title=', <tt>SHIFT</tt> choose')
        self.get_box().pack_start(self.tabcompletion, expand=True)
        self.get_box().pack_start(gtk.HSeparator(), expand=False)
        self.history = TextMatchDisplay(title=u'<b>History</b> - %s matches <b>(</b><tt>\u2191</tt><b>)</b>',
                                        context=context, init_dispsize=1)
        self.get_box().pack_start(self.history, expand=True)
        self.__idle_history_search_id = 0
        self.__search = None
        self.__saved_input = None
        self.__idle_reposition_id = 0

    def __queue_reposition(self):
        if self.__idle_reposition_id > 0:
            return
        self.__idle_reposition_id = gobject.idle_add(self.__idle_reposition)

    def __idle_reposition(self):
        self.reposition()
        self.__idle_reposition_id = 0
        return False

    def set_tab_completion(self, prefix, generator):
        _logger.debug("new tab prefix: %s search: %s", prefix, generator)
        self.__tabprefix = prefix
        if self.history.get_expanded():
            generator = None
        self.tabcompletion.set_compact(generator is not None)
        self.tabcompletion.set_generator(generator)
        if (generator is not None) and not self.tabcompletion.empty():
            self.tabcompletion.show_all()
            self.tabcompletion.expand()
            self.show()
        else:
            self.__check_hide()
        self.__queue_reposition()

    def get_history_search(self):
        return self.__search

    def __check_hide(self):
        hidden = 0
        if self.history.empty():
            self.history.hide()
            hidden += 1
        if self.tabcompletion.empty():
            self.tabcompletion.hide()
            hidden += 1
        _logger.debug("hidden: %d", hidden)
        if hidden == 2:
            self.hide()
            return False
        return True

    def set_history_search(self, search, now=False):
        self.__search = search
        self.__selected = None
        self.__saved_input = None
        _logger.debug("new history search: %s", search)
        if not now:
            self.history.set_compact(not self.__search)
            if search and self.__idle_history_search_id == 0:
                _logger.debug("queuing idle history search for '%s'", search)
                self.__idle_history_search_id = gobject.timeout_add(300, self.__idle_do_history_search)
            elif not search:
                if self.__idle_history_search_id > 0:
                    gobject.source_remove(self.__idle_history_search_id)
                    self.__idle_history_search_id = 0
                self.history.set_generator(None)
                self.__check_hide()
        else:
            if self.__idle_history_search_id > 0:
                gobject.source_remove(self.__idle_history_search_id)
            self.__idle_do_history_search()
            self.tabcompletion.hide()
            self.history.expand()
            self.__queue_reposition()

    def __idle_do_history_search(self):
        self.__idle_history_search_id = 0
        if self.__search:
            histsrc = self.__context.history.search_commands(self.__search)
        else:
            histsrc = self.__tabhistory
        self.history.set_generator(self.__generate_history(histsrc))
        visible = self.__check_hide()
        if visible:
            self.show()
            self.__queue_reposition()

    def __generate_history(self, src):
        for histitem in src:
            if self.__search:
                idx = histitem.find(self.__search)
                if idx < 0:
                    continue
                compl = Completion(histitem, idx, len(self.__search))
                yield compl
            else:
                yield Completion(histitem, 0, 0)

    def select_history_next(self, curtext):
        res = self.history.select_next(curtext)
        self.__queue_reposition()
        return res

    def select_history_prev(self):
        res = self.history.select_prev()
        self.__queue_reposition()
        return res

    def tab_is_singleton(self):
        return self.tabcompletion.itemcount() == 1

    def tab_get_prefix(self):
        return self.__tabprefix

    def select_tab_next(self):
        res = self.tabcompletion.select_next()
        self.__queue_reposition()
        return res

    def select_tab_prev(self):
        res = self.tabcompletion.select_prev()
        self.__queue_reposition()
        return res

