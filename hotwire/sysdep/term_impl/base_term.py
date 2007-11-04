# -*- tab-width: 4 -*-
import os,sys,platform,logging

import gtk,gobject,pango

import hotwire_ui.widgets as hotwidgets
from hotwire.state import Preferences

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
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='EditMenu'>
      <menuitem action='Copy'/>
      <menuitem action='Paste'/>
    </menu>
    <menu action='ViewMenu'>
      <menuitem action='ToWindow'/>
    </menu>
    <menu action='PrefsMenu'>
      <menuitem action='SetForeground'/>
      <menuitem action='SetBackground'/>      
    </menu>
    <!-- <menu action='ControlMenu'>
      <menuitem action='SplitWindow'/>
    </menu> -->
  </menubar>
</ui>"""         
        self.__actions = [
            ('Copy', None, '_Copy', '<control><shift>c', 'Copy selected text', self.__copy_cb),
            ('Paste', None, '_Paste', '<control><shift>V', 'Paste text', self.__paste_cb),
            ('ToWindow', None, '_To Window', '<control><shift>N', 'Turn into new window', self.__split_cb),
            ('SetForeground', None, 'Set _Foreground', None, 'Change the foreground color', self.__set_foreground_cb),
            ('SetBackground', None, 'Set _Background', None, 'Change the background color', self.__set_background_cb),                        
        ]
        self.__action_group = gtk.ActionGroup('TerminalActions')
        self.__action_group.add_actions(self.__actions)
        self._stream = stream
        self.__title = title
        self.__header = gtk.HBox()
        self.__msg = gtk.Label('')
        self.__pid = None
        self.__exited = False
        self.__header.pack_start(hotwidgets.Align(self.__msg, xalign=1.0), expand=False)
        self.__msg.set_property('xalign', 1.0)

        self.pack_start(self.__header, expand=False)

        self.__termbox = gtk.HBox()
        self.pack_start(self.__termbox, expand=True)  

        self.__term = None
        prefs = Preferences.getInstance()
        prefs.connect('tree-changed', self.__on_prefs_tree)        
        
    def get_ui(self):
        return (self.__ui_string, self.__action_group)

    def _selection_changed(self, have_selection):
        self.__action_group.get_action('Copy').set_sensitive(have_selection)

    def __copy_cb(self, a):
        _logger.debug("doing copy")
        self.copy()

    def __paste_cb(self, a):
        _logger.debug("doing paste")        
        self.paste()
        
    def __set_foreground_cb(self, a):
        self.__colorpick(True)
        
    def __set_background_cb(self, a):
        self.__colorpick(False)
        
    def __on_prefs_tree(self, prefs, root):
        if root != 'term':
            return
        self.__sync_prefs()    
    
    def __sync_prefs(self, *args):
        prefs = Preferences.getInstance()
        fg = prefs.get_pref('term.foreground', default='#000')
        bg = prefs.get_pref('term.background', default='#FFF')
        _logger.debug("got fg=%s, bg=%s", fg, bg)
        self.set_color(True, gtk.gdk.color_parse(fg))
        self.set_color(False, gtk.gdk.color_parse(bg))
        
    def _sync_prefs(self):
        self.__sync_prefs()      
        
    def __colorpick(self, is_foreground):
        dlg = gtk.ColorSelectionDialog(is_foreground and 'Choose Foreground' or 'Choose Background')
        colorsel = dlg.colorsel
        prefs = Preferences.getInstance()
        if is_foreground:
            curcolor_str = prefs.get_pref('term.foreground', default='#000')
        else:
            curcolor_str = prefs.get_pref('term.background', default='#FFF')
        curcolor = gtk.gdk.color_parse(curcolor_str) 
        colorsel.set_property('current-color', curcolor)
        result = dlg.run()
        color = colorsel.get_property('current-color')
        dlg.destroy()     
        if result != gtk.RESPONSE_OK:
            _logger.debug("got response %s", result)
            return
        
        color_str = '#%04X%04X%04X' % (color.red, color.green, color.blue)
        if is_foreground:
            prefs.set_pref('term.foreground', color_str)
        else:
            prefs.set_pref('term.background', color_str)

    def _pack_terminal(self, termwidget):
        self.__term = termwidget
        self.__termbox.add(termwidget)

    def _set_pid(self, pid):
        self.__pid = pid
        self.__msg.set_text('Running (pid %s)' % (pid,))

    def __split_cb(self, a):
        from hotwire_ui.shell import locate_current_window
        hwin = locate_current_window(self)        
        self.emit('closed')
        hwin.new_win_widget(self, self.__title)

    def _on_child_exited(self, term):
        _logger.debug("Caught child exited")
        self.__exited = True
        self.__msg.set_markup('<span foreground="red">Exited</span>')
        self.emit('closed')

    def close(self):
        raise NotImplementedError()
