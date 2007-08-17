# -*- tab-width: 4 -*-
import os,sys,platform,logging

import gtk,gobject,pango

import hotwire_ui.widgets as hotwidgets

_logger = logging.getLogger("hotwire.sysdep.Terminal")

class BaseTerminal(object):
    def open_terminal_window(self, stream, title):
        pass

    def get_terminal_widget(self, stream, title):
        raise NotImplementedError()

    def open_terminal_window_cmd(self, cwd, cmd, title):
        pass

    def get_terminal_widget_cmd(self, cwd, cmd, title):
        raise NotImplementedError()


class TerminalWidget(gtk.VBox):
    __gsignals__ = {
        "closed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }
    def __init__(self, stream=None, title=''):
        super(TerminalWidget, self).__init__()
        self._stream = stream
        self.__title = title
        self.__header = gtk.HBox()
        self.__mergelink = hotwidgets.Link()
        self.__mergelink.set_alignment(0, 0.5)
        self.__mergelink.set_text('Split as window')
        self.__mergelink_clickid = self.__mergelink.connect('clicked', self.__on_split_clicked)
        self.__header.pack_start(self.__mergelink, expand=True)
        self.__msg = gtk.Label('')
        self.__pid = None
        self.__exited = False
        self.__header.pack_start(hotwidgets.Align(self.__msg, xalign=1.0), expand=False)
        self.__msg.set_property('xalign', 1.0)

        self.pack_start(self.__header, expand=False)

        self.__termbox = gtk.HBox()
        self.pack_start(self.__termbox, expand=True)

        self.__term = None

    def copy(self):
        self.__term.copy()

    def paste(self):
        self.__term.paste()

    def on_mouse_press(self, e):
        _logger.debug("button press %s", e)
        if e.button == 3:
            menu = gtk.Menu()
            menuitem = gtk.MenuItem('Copy')
            menuitem.connect("activate", self.__on_copy_activated)
            menu.append(menuitem)
            menuitem = gtk.MenuItem('Paste')
            menuitem.connect("activate", self.__on_paste_activated)
            menu.append(menuitem)
            menu.show_all()
            menu.popup(None, None, None, e.button, e.time)
            return True
        return False

    def __on_copy_activated(self, menu):
        self.copy()

    def __on_paste_activated(self, menu):
        self.paste()
        
    def _pack_terminal(self, termwidget):
        self.__term = termwidget
        self.__termbox.add(termwidget)

    def _set_pid(self, pid):
        self.__pid = pid
        self.__msg.set_text('Running (pid %s)' % (pid,))

    def __on_split_clicked(self, l):
        self.emit('closed')
        self.__mergelink.hide()
        w = gtk.Window(gtk.WINDOW_TOPLEVEL)
        w.set_title(self.__title)
        w.add(self)
        w.show_all()
        self.__mergelink.hide()

    def _on_child_exited(self, term):
        _logger.debug("Caught child exited")
        self.__exited = True
        self.__msg.set_markup('<span foreground="red">Exited</span>')
        self.emit('closed')

    def close(self):
        raise NotImplementedError()

    def controls_copypaste(self):
        return False

