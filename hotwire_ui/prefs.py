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

import os, sys, re, logging, string

import gtk, gobject, pango

from hotwire.state import Preferences
from hotwire.logutil import log_except
import hotwire_ui.widgets as hotwidgets

_logger = logging.getLogger("hotwire.ui.Preferences")
            
class PrefsWindow(gtk.Dialog):
    def __init__(self):
        super(PrefsWindow, self).__init__(title=_('Preferences'),
                                          parent=None,
                                          flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_ACCEPT))
        
        prefs = Preferences.getInstance()
        
        self.connect('response', lambda *args: self.hide())
        self.connect('delete-event', self.hide_on_delete)
                
        self.set_has_separator(False)
        self.set_border_width(5)
        
        self.__vbox = gtk.VBox()
        self.vbox.add(self.__vbox)   
        self.vbox.set_spacing(2)
        self.__notebook = gtk.Notebook()
        self.__vbox.add(self.__notebook)

        self.__general_tab = gtk.VBox()
        self.__notebook.append_page(self.__general_tab)
        self.__notebook.set_tab_label_text(self.__general_tab, _('General'))
        
        vbox = gtk.VBox()
        vbox.set_border_width(12)
        vbox.set_spacing(6)                   
        label = gtk.Label()
        label.set_markup('<b>%s</b>' % (_('Interface'),))
        label.set_alignment(0.0, 0.0)
        vbox.pack_start(hotwidgets.Align(label), expand=False)
        self.__general_tab.pack_start(vbox, expand=False)
        menuaccess = gtk.CheckButton(_('Disable menu access keys'))
        menuaccess.set_property('active', not prefs.get_pref('ui.menuaccels', default=True))
        menuaccess.connect('toggled', self.__on_menuaccess_toggled)        
        vbox.pack_start(hotwidgets.Align(menuaccess, padding_left=12), expand=False)
        readline = self.__readline = gtk.CheckButton(_('Enable Unix "Readline" keys (Ctrl-A, Alt-F, Ctrl-K, etc.)'))
        readline.set_property('active', prefs.get_pref('ui.emacs', default=False))
        readline.connect('toggled', self.__on_readline_toggled)        
        vbox.pack_start(hotwidgets.Align(readline, padding_left=12), expand=False)
        self.__sync_emacs_sensitive()        
        
        self.__term_tab = gtk.VBox()
        self.__notebook.append_page(self.__term_tab)
        self.__notebook.set_tab_label_text(self.__term_tab, _('Terminal'))   
        
        vbox = gtk.VBox()
        vbox.set_border_width(12)
        vbox.set_spacing(6) 
        label = gtk.Label()
        label.set_markup('<b>%s</b>' % (_('Interface'),))
        label.set_alignment(0.0, 0.0)
        vbox.pack_start(label, expand=False)
        self.__term_tab.pack_start(vbox, expand=False)
        
        hbox = gtk.HBox()
        vbox.pack_start(hotwidgets.Align(hbox, padding_left=12), expand=False)
        sg = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        fg_label = gtk.Label(_('Foreground Color: '))
        sg.add_widget(fg_label)
        hbox.pack_start(fg_label, expand=False)
        fg_color = self.__fg_color = gtk.ColorButton(gtk.gdk.color_parse(prefs.get_pref('term.foreground', default='#000')))
        hbox.pack_start(fg_color, expand=False)
        fg_color.connect('color-set', self.__on_fg_bg_changed)
        
        hbox = gtk.HBox()
        vbox.pack_start(hotwidgets.Align(hbox, padding_left=12), expand=False)
        bg_label = gtk.Label(_('Background Color: '))
        sg.add_widget(bg_label)
        hbox.pack_start(bg_label, expand=False)
        bg_color = self.__bg_color = gtk.ColorButton(gtk.gdk.color_parse(prefs.get_pref('term.background', default='#FFF')))
        hbox.pack_start(bg_color, expand=False)
        bg_color.connect('color-set', self.__on_fg_bg_changed)
        
    def __on_fg_bg_changed(self, cb):
        prefs = Preferences.getInstance()        
        def sync_color_pref(button, prefname):
            color = button.get_color()
            color_str = '#%04X%04X%04X' % (color.red, color.green, color.blue)
            prefs.set_pref(prefname, color_str)
        sync_color_pref(self.__fg_color, 'term.foreground')
        sync_color_pref(self.__bg_color, 'term.background')
        
    def __sync_emacs_sensitive(self):
        prefs = Preferences.getInstance()
        accels = prefs.get_pref('ui.menuaccels', default=True)
        if accels and prefs.get_pref('ui.emacs', default=False): 
            prefs.set_pref('ui.emacs', False)  
            self.__readline.set_property('active', False)
        self.__readline.set_sensitive(not accels)                  
        
    def __on_menuaccess_toggled(self, cb):
        active = cb.get_property('active')
        prefs = Preferences.getInstance()
        prefs.set_pref('ui.menuaccels', not active)
        self.__sync_emacs_sensitive()
        
    def __on_readline_toggled(self, cb):
        active = cb.get_property('active')
        prefs = Preferences.getInstance()
        prefs.set_pref('ui.emacs', active)   
