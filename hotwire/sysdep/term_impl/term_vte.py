import os,sys,threading,pty,logging

import gtk, gobject, pango
import vte
import gconf

import hotwire_ui.widgets as hotwidgets
from hotwire.sysdep.term_impl.base_term import BaseTerminal, TerminalWidget
from hotwire.logutil import log_except
from hotwire.async import MiniThreadPool

_logger = logging.getLogger("hotwire.sysdep.Terminal.Vte")

class VteTerminal(BaseTerminal):
    def get_terminal_widget(self, stream, title):
        return VteTerminalWidget(stream=stream, title=title)

    def get_terminal_widget_cmd(self, cwd, cmd, title):
        return VteTerminalWidget(cwd=cwd, cmd=cmd, title=title)

class VteTerminalScreen(gtk.Bin):
    def __init__(self):
        super(VteTerminalScreen, self).__init__()
        self.term = vte.Terminal()
        self.__termbox = gtk.HBox()
        self.__scroll = gtk.VScrollbar(self.term.get_adjustment())
        self.__termbox.pack_start(hotwidgets.Border(self.term))
        self.__termbox.pack_start(self.__scroll, False)
        self.add(self.__termbox)

    def do_size_request(self, req):
        (w,h) = self.__termbox.size_request()
        req.width = w
        req.height = h

    def do_size_allocate(self, alloc):
        self.allocation = alloc
        wid_req = self.__termbox.size_allocate(alloc)

gobject.type_register(VteTerminalScreen)

class VteTerminalWidget(TerminalWidget):
    def __init__(self, cwd=None, cmd=None, **kwargs):
        self.__screen = screen = VteTerminalScreen()
        self.__term = screen.term        
        
        super(VteTerminalWidget, self).__init__(**kwargs)

        self._pack_terminal(screen)

        # Various defaults
        self.__term.set_emulation('xterm')
        self.__term.set_allow_bold(True)
        self.__term.set_size(80, 24)
        self.__term.set_mouse_autohide(True)

        self.__term.connect('popup_menu', self.__on_popup_menu)
        self.__term.connect('selection-changed', self.__on_selection_changed)

        # Use Gnome font 
        gconf_client = gconf.client_get_default() 
        mono_font = gconf_client.get_string('/desktop/gnome/interface/monospace_font_name')
        _logger.debug("Using font '%s'", mono_font)
        font_desc = pango.FontDescription(mono_font)
        self.__term.set_font(font_desc)

        # Colors
        fg = self.__term.style.text[gtk.STATE_NORMAL]
        bg = self.__term.style.base[gtk.STATE_NORMAL]
        self.__term.set_default_colors()
        self.__term.set_color_background(bg)
        self.__term.set_color_foreground(fg)
        self.__term.set_color_bold(fg)
        self.__term.set_color_dim(fg)

        self._selection_changed(False)

        self._sync_prefs()

        if self._stream:
            master, slave = pty.openpty()
            self.__master = master
            self.__slave = slave
            self.__term.set_pty(self.__master)
            _logger.debug("Created pty master: %d slave: %d", master, slave)
            MiniThreadPool.getInstance().run(self.__fd_to_stream, args=(self.__slave, self._stream))
            MiniThreadPool.getInstance().run(self.__stream_to_fd, args=(self._stream, self.__slave))
        else:
            self._stream = None
            # http://code.google.com/p/hotwire-shell/issues/detail?id=35
            # We do the command in an idle to hopefully have more state set up by then;
            # For example, "top" seems to be sized correctly on the first display
            # this way
            gobject.timeout_add(250, self.__idle_do_cmd_fork, cmd, cwd)
            
    @log_except(_logger)
    def __idle_do_cmd_fork(self, cmd, cwd):
        _logger.debug("Forking cmd: %s", cmd)
        self.__term.connect("child-exited", self._on_child_exited)
        if cmd:
            pid = self.__term.fork_command('/bin/sh', ['/bin/sh', '-c', cmd], directory=cwd)
        else:
            pid = self.__term.fork_command(directory=cwd)
        self._set_pid(pid)

    def __fd_to_stream(self, fd, stream):
        while True:
            buf = os.read(fd,4096)
            if buf == '':
                break
            stream.send(buf)

    def __stream_to_fd(self, stream, fd):
        while True:
            buf = stream.recv(4096)
            if buf == '':
                break
            os.write(fd, buf)
        gobject.idle_add(lambda: self.close())

    def close(self):
        if self._stream:
            _logger.debug("Closing stream")
            self._stream.close()
            os.close(self.__master)
            os.close(self.__slave)
            self._stream = None

    def do_dispose(self):
        self.__term = None

    def get_term_geometry(self):
        cw = self.__term.get_char_width()
        ch = self.__term.get_char_height()
        return (cw, ch, self.__term.get_padding())
        
    def __on_popup_menu(self, *args):
        menu = gtk.Menu()
        mi = gtk.MenuItem(label='Copy')
        mi.connect('activate', self.copy)
        menu.append(mi)
        mi = gtk.MenuItem(label='Paste')
        mi.connect('activate', self.paste)
        menu.append(mi)
        menu.show_all()
        menu.popup(None, None, None, 0, gtk.get_current_event_time())
        
    def __on_selection_changed(self, *args):
        self._selection_changed(self.__term.get_has_selection())

    def copy(self, *args):
        _logger.debug("got copy")
        self.__term.copy_clipboard()

    def paste(self, *args):
        _logger.debug("got paste")
        self.__term.paste_clipboard()
        
    def set_color(self, is_foreground, color):
        if is_foreground:
            self.__term.set_color_foreground(color)
        else:
            self.__term.set_color_background(color)        

def getInstance():
    return VteTerminal()
