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

import os,sys

# Older webbrowser.py didn't check gconf
if sys.version_info[0] == 2 and sys.version_info[1] < 6:
    import hotwire.externals.webbrowser as webbrowser
else:
    import webbrowser

import gtk, gobject, pango

import hotwire
from hotwire.sysdep import is_unix, is_windows
from hotwire.text import MarkupText
import hotwire_ui.widgets as hotwidgets
from hotwire_ui.render import ObjectsRenderer, ClassRendererMapping

class SearchArea(gtk.HBox):
    __gsignals__ = {
        "close" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
    }

    def __init__(self, textview, **kwargs):
        super(SearchArea, self).__init__(**kwargs)

        self.__textview = textview
        self.__idle_search_id = 0

        close = gtk.Button()
        close.set_focus_on_click(False)
        close.set_relief(gtk.RELIEF_NONE)
        img = gtk.Image()
        img.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_SMALL_TOOLBAR)
        close.add(img)
        close.connect('clicked', lambda b: self.__do_close())        
        self.pack_start(close, expand=False)
        self.__input = gtk.Entry()
        self.__input.connect("notify::text", lambda *args: self.__on_input_changed())
        self.__input.connect("key-press-event", lambda i, e: self.__on_input_keypress(e))
        self.pack_start(self.__input, expand=False)
        self.__next = gtk.Button('_Next', gtk.STOCK_GO_DOWN)
        self.__next.set_focus_on_click(False)
        self.__next.connect("clicked", lambda b: self.__do_next())
        self.pack_start(self.__next, expand=False)
        self.__prev = gtk.Button('_Prev', gtk.STOCK_GO_UP)
        self.__prev.set_focus_on_click(False)
        self.__prev.connect("clicked", lambda b: self.__do_prev())
        self.pack_start(self.__prev, expand=False)
        self.__msgbox = gtk.HBox()
        self.__msg_icon = gtk.Image()
        self.__msgbox.pack_start(self.__msg_icon, False)
        self.__msg = gtk.Label()
        self.__msgbox.pack_start(self.__msg, True)
        self.pack_start(self.__msgbox, expand=False)

    def __on_input_keypress(self, e):
        if e.keyval == gtk.gdk.keyval_from_name('Escape'):
            self.__do_close()
            return True
        elif e.keyval in (gtk.gdk.keyval_from_name('Down'), gtk.gdk.keyval_from_name('Return')):
            self.__do_next()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Up'):
            self.__do_prev()
            return True
        return False

    def __on_input_changed(self):
        curtext = self.__input.get_property('text')
        if not curtext:
            return
        if self.__idle_search_id == 0:
            self.__idle_search_id = gobject.timeout_add(250, self.__idle_do_search)
        self.__clear_search_selection()

    def __idle_do_search(self):
        self.__idle_search_id = 0
        self.__search()
        return False

    def __do_close(self):
        self.reset()
        self.__clear_search_selection()
        self.hide()
        self.emit("close")

    def focus(self):
        self.__input.grab_focus()

    def __clear_search_selection(self):
        buf = self.__textview.get_buffer()
        buf.select_range(buf.get_start_iter(), buf.get_start_iter())
        mark = buf.get_mark("search_start")
        if mark:
            buf.delete_mark(mark)
        mark = buf.get_mark("search_end")
        if mark:
            buf.delete_mark(mark)

    def reset(self):
        self.__input.set_property('text', '')

    def __search(self, start_iter=None, loop=False, forward=True):
        if start_iter:
            iter = start_iter
        elif forward:
            iter = self.__textview.get_buffer().get_start_iter()
        else:
            iter = self.__textview.get_buffer().get_end_iter()
        buf = self.__textview.get_buffer()
        text = self.__input.get_text()
        if not loop:
            self.__msg_icon.clear()
            self.__msg.set_text('')
        else:
            self.__msg_icon.set_from_stock(gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.__msg.set_text('Search wrapped from top')
        if not text:
            return
        if forward:
            searchres = iter.forward_search(text, 0)
        else:
            searchres = iter.backward_search(text, 0)
        if searchres:
            (start, end) = searchres
            buf.select_range(start, end)
            start_mark = buf.create_mark("search_start", start, False)
            end_mark = buf.create_mark("search_end", end, False)
            self.__textview.scroll_mark_onscreen(start_mark)
        elif (start_iter is not None) and (not loop):
            self.__search(loop=True, forward=forward)
        else:
            self.__msg_icon.set_from_stock(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.__msg.set_text('No matches found')

    def __search_interactive(self, forward):
        if self.__idle_search_id > 0:
            gobject.source_remove(self.__idle_search_id)
            self.__idle_search_id = 0
        buf = self.__textview.get_buffer()
        if forward:
            mark = buf.get_mark("search_end")
        else:
            mark = buf.get_mark("search_start")
        if mark:
            self.__search(start_iter=buf.get_iter_at_mark(mark), forward=forward)
        else:
            self.__search(forward=forward)

    def __do_next(self):
        self.__search_interactive(True)

    def __do_prev(self):
        self.__search_interactive(False)
        

class InputArea(gtk.HBox):
    __gsignals__ = {
        "close" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "object-input" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,gobject.TYPE_BOOLEAN)),  
    }

    def __init__(self, textview, **kwargs):
        super(InputArea, self).__init__(**kwargs)

        self.__textview = textview

        close = gtk.Button()
        close.set_focus_on_click(False)
        close.set_relief(gtk.RELIEF_NONE)
        img = gtk.Image()
        img.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_SMALL_TOOLBAR)
        close.add(img)
        close.connect('clicked', lambda b: self.__do_close())        
        self.pack_start(close, expand=False)
        self.__input = gtk.Entry()
        self.__input.connect("key-press-event", lambda i, e: self.__on_input_keypress(e))
        hbox = gtk.HBox()
        hbox.pack_start(self.__input, expand=True)
        self.__send= gtk.Button('_Send', gtk.STOCK_OK)
        self.__send.set_focus_on_click(False)
        self.__send.connect("clicked", lambda b: self.__do_send())
        hbox.pack_start(self.__send, expand=False)
        self.__password_button = gtk.CheckButton(label='_Password mode')
        self.__password_button.connect('toggled', self.__on_password_toggled)
        self.__password_button.set_focus_on_click(False)
        hbox.pack_start(hotwidgets.Align(self.__password_button, padding_left=8), expand=False)
        self.pack_start(hotwidgets.Align(hbox, xscale=0.75), expand=True)        

    def __on_input_keypress(self, e):
        if e.keyval == gtk.gdk.keyval_from_name('Escape'):
            self.__do_close()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Return'):
            self.__do_send()
            return True      
        return False
    
    def __on_password_toggled(self, tb):
        self.__input.set_visibility(not tb.get_active())

    def __do_close(self):
        self.reset()
        self.hide()
        self.emit("close")
        
    def __do_send(self):
        self.emit('object-input', self.__input.get_property('text'), self.__password_button.get_active())
        self.reset()

    def focus(self):
        self.__input.grab_focus()

    def reset(self):
        self.__input.set_property('text', '')

class UnicodeRenderer(ObjectsRenderer):
    def __init__(self, context, monospace=True, **kwargs):
        super(UnicodeRenderer, self).__init__(context, **kwargs)
        self._buf = hotwidgets.BasicMarkupTextBuffer()
        self.__text = gtk.TextView(self._buf)
        if monospace:
            self.__text.modify_font(pango.FontDescription("monospace"))
        self.__text.connect('event-after', self.__on_event_after)
        self._buf.connect('mark-set', self.__on_mark_set)
        self.__term = None
        self.__bufcount = 0
        self.__wrap_lines = False
        self.__have_selection = False
        self.__sync_wrap()
        self.__text.set_editable(False)
        self.__text.set_cursor_visible(False)
        self.__text.unset_flags(gtk.CAN_FOCUS)
        self.__empty = True
        self.__bytecount = 0
        self._buf.insert_markup("<i>(No output)</i>")
        self.__search = SearchArea(self.__text)
        self.__inputarea = InputArea(self.__text)
        self.__inputarea.connect('object-input', self.__on_object_input)
        self.__text.connect('populate-popup', self.__on_populate_popup)
        self.__links = {} # internal hyperlinks
        self.__support_links = False
        self.__hovering_over_link = False
        
    def __on_object_input(self, ia, o, pwmode):
        if not pwmode:
            self.append_obj(o)

    def __on_event_after(self, textview, e):
        if e.type != gtk.gdk.BUTTON_RELEASE:
            return;
        if e.button != 1:
            return;
        (x, y) = self.__text.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, int(e.x), int(e.y))
        iter = self.__text.get_iter_at_location(x, y)
        for tag in iter.get_tags():
            if tag.get_property('name') == 'link':
                iterstart = iter.copy()
                iterend = iter.copy()
                iterstart.backward_to_tag_toggle(tag)
                iterend.forward_to_tag_toggle(tag)
                webbrowser.open(self.__links[self._buf.get_slice(iterstart, iterend)])
                break

    def append_link(self, text, target):
        self.__links[text] = target
        if not self.__support_links:
            self.__install_link_handlers()
            self.__support_links = True
        (iterstart, iterend) = self._buf.get_bounds()
        self._buf.insert_with_tags_by_name(iterend, text, 'link')

    def __install_link_handlers(self):
        self.__text.connect('motion-notify-event', self.__on_motion_notify)
        self.__text.connect('visibility-notify-event', self.__on_visibility_notify)

    def __on_motion_notify(self, text, e):
        (x, y) = self.__text.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, int(e.x), int(e.y))
        self.__update_cursor_for_coords(x, y)
        (x, y, state) = self.__text.window.get_pointer()
        
    def __on_visibility_notify(self, text, vis):
        (x, y) = self.__text.get_pointer()
        self.__update_cursor_for_coords(x, y)
        
    def __on_mark_set(self, *args):
        have_sel = self._buf.get_has_selection()
        if have_sel == self.__have_selection:
            return
        self.context.get_ui().get_action('/Menubar/EditMenu/EditMenuAdditions/Copy').set_sensitive(have_sel)
        self.__have_selection = have_sel

    def __update_cursor_for_coords(self, x, y):
        iter = self.__text.get_iter_at_location(x, y)
        hovering = False
        for tag in iter.get_tags():
            if tag.get_property('name') == 'link':
                hovering = True
                break
        if hovering != self.__hovering_over_link:
            self.__hovering_over_link = hovering
            if hovering:
                cursor = gtk.gdk.Cursor(self.__text.get_display(), gtk.gdk.HAND2)
            else:
                cursor = None
            window = self.__text.get_window(gtk.TEXT_WINDOW_TEXT)
            window.set_cursor(cursor)
        
    def get_widget(self):
        return self.__text

    def get_search(self):
        return self.__search

    def get_status_str(self):
        return "%d bytes" % (self.__bytecount,)

    def get_objects(self):
        iter = self._buf.get_start_iter()
        if iter == self._buf.get_end_iter():
            return
        startline = iter.copy()
        not_at_end = iter.forward_line()
        iter.backward_char()
        yield self._buf.get_slice(startline, iter)
        iter.forward_char()
        while not_at_end:
            startline = iter
            iter = iter.copy()
            not_at_end = iter.forward_line()
            iter.backward_char()
            yield self._buf.get_slice(startline, iter)
            iter.forward_char()

    def get_opt_formats(self):
        if is_unix():
            return ['x-filedescriptor/special', 'text/chunked']
        else:
            return ['text/chunked']

    def __append_chunk(self, obj):
        buf = self._buf
        if self.__empty:
            buf.delete(buf.get_start_iter(), buf.get_end_iter())
            self.__empty = False
        ## Initial support for terminal codes.  Only 08 is handled now.
        start = 0
        olen = len(obj)
        self.__bytecount += olen
        ## This algorithm groups consecutive 8 bytes together to do the delete in one pass. 
        while True:
            idx = obj.find('\x08', start)
            if idx < 0:
                break
            tbuf = obj[start:idx]
            buf.insert(buf.get_end_iter(), tbuf)
            previdx = idx
            while idx < olen and obj[idx] == '\x08':
                idx += 1
            end = buf.get_end_iter().copy()
            end.backward_chars(idx-previdx)
            buf.delete(end, buf.get_end_iter())
            start = idx
        buf.insert(buf.get_end_iter(), start and obj[start:] or obj)
        self.emit('status-changed')

    def append_obj(self, obj, fmt=None):
        if fmt == 'text/chunked':
            self.__append_chunk(obj)
            return
        elif fmt == 'x-filedescriptor/special':
            self.__monitor_fd(obj)
            return        
        if self.__empty:
            self._buf.delete(self._buf.get_start_iter(), self._buf.get_end_iter())
            self.__empty = False
        allinsert_start = self._buf.get_start_iter().get_offset()
        if isinstance(obj, MarkupText):
            tags = []
            prev_tagend = 0
            olen = len(obj)
            for (tagname, start, end) in obj.markup:
               self._buf.insert(self._buf.get_end_iter(), obj[prev_tagend:start])
               real_end = (end == -1) and olen or end
               self._buf.insert_with_tags_by_name(self._buf.get_end_iter(), obj[start:real_end], tagname)
               prev_tagend = real_end
            self._buf.insert(self._buf.get_end_iter(), obj[prev_tagend:])
            self.__bytecount += olen
        else:
            self.__append_chunk(obj)
        self._buf.insert(self._buf.get_end_iter(), '\n')

    def __spawn_terminal(self, fd, buf):
        w = gtk.Window(gtk.WINDOW_TOPLEVEL)
        from hotvte.vteterm import VteTerminalScreen
        self.__term = term = VteTerminalScreen()
        w.add(term)
        import termios
        attrs = termios.tcgetattr(fd)
        attrs[1] = attrs[1] & (termios.ONLCR)
        attrs[3] = attrs[3] & (termios.ECHO)
        termios.tcsetattr(fd, termios.TCSANOW, attrs)                 
        term.term.set_pty(fd)
        # Undo our newline stripping
        buf = buf.replace('\n', '\r\n')
        term.term.feed_child(buf)
        w.show_all()        

    def __on_fd(self, src, condition):
        if (condition & gobject.IO_IN):
            buf = os.read(src, 8192)
            self.__bufcount += 1
            # TODO: improve this further
            if (not self.__term) and self.__bufcount < 3 and buf.find('\x1b[') >= 0:
                self.__spawn_terminal(src, buf)
                return False
            else:
                self.__append_chunk(buf)
        if ((condition & gobject.IO_HUP) or (condition & gobject.IO_ERR)):
            try:
                os.close(src)
            except:
                pass
            return False
        return True        
        
    def __monitor_fd(self, fd):
        gobject.io_add_watch(fd, gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP, self.__on_fd, priority=gobject.PRIORITY_LOW)

    def get_autoscroll(self):
        return True

    def can_copy(self):
        return self._buf.get_selection_bounds()

    def do_copy(self):
        bounds = self._buf.get_selection_bounds()
        if bounds:
            self._buf.copy_clipboard(gtk.Clipboard())
            return True
        return False
        
    def __sync_wrap(self):
        self.__text.set_wrap_mode(self.__wrap_lines and gtk.WRAP_CHAR or gtk.WRAP_NONE)

    def __on_toggle_wrap(self, menuitem):
        self.__wrap_lines = not self.__wrap_lines
        self.__sync_wrap()

    def __on_populate_popup(self, textview, menu):
        menuitem = gtk.SeparatorMenuItem()
        menuitem.show_all()
        menu.prepend(menuitem)
        menuitem = gtk.CheckMenuItem(label='_Wrap lines', use_underline=True) 
        menuitem.set_active(self.__wrap_lines)
        menuitem.connect("activate", self.__on_toggle_wrap)
        menuitem.show_all()
        menu.prepend(menuitem)                   
        menuitem = self.context.get_ui().get_action('/Menubar/EditMenu/EditMenuAdditions/Input').create_menu_item()
        menuitem.show_all()
        menu.prepend(menuitem) 

    def supports_input(self):
        return True
    
    def get_input(self):
        return self.__inputarea

ClassRendererMapping.getInstance().register(unicode, UnicodeRenderer)
ClassRendererMapping.getInstance().register(str, UnicodeRenderer) # for now
