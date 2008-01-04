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

import os, sys, logging, StringIO, traceback, inspect, locale

import cairo, gtk, gobject, pango

from hotwire.util import ellipsize
import hotwire_ui.widgets as hotwidgets

_logger = logging.getLogger("hotwire.ui.OInspect")

class InspectWindow(gtk.Window):
    def __init__(self, obj):
        gtk.Window.__init__(self, type=gtk.WINDOW_TOPLEVEL)
        vbox = gtk.VBox()
        self.add(vbox)
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <menuitem action='Close'/>
    </menu>
  </menubar>
</ui>
"""
        self.__create_ui()
        vbox.pack_start(self._ui.get_widget('/Menubar'), expand=False)

        self.__orepr = gtk.Label()
        vbox.pack_start(self.__orepr, expand=False)
        self.__members_model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)        
        self.__membersview = gtk.TreeView(self.__members_model)
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.add(self.__membersview)
        vbox.pack_start(scroll, expand=True)
        colidx = self.__membersview.insert_column_with_attributes(-1, _('Name'),
                                                                  hotwidgets.CellRendererText(),
                                                                  text=0)
        colidx = self.__membersview.insert_column_with_data_func(-1, _('Member'),
                                                                 hotwidgets.CellRendererText(),
                                                                 self.__render_member)
        col = self.__membersview.get_column(colidx-1)
        col.set_spacing(0)
        col.set_resizable(True)        
        col = self.__membersview.get_column(colidx-1)
        col.set_spacing(0)
        col.set_resizable(True)

        self.set_title(_('Object inspect: %s - Hotwire')  % (ellipsize(repr(obj), 30),))
        self.set_size_request(640, 480)
        
        self.__set_object(obj)
        
    def __set_object(self, obj):
        self.__orepr.set_markup(_('<b>Object</b>: %s')  % (gobject.markup_escape_text(repr(obj),)))
        for name,member in sorted(inspect.getmembers(obj), lambda a,b: locale.strcoll(a[0],b[0])):
            self.__members_model.append((name, member))
            
    def __render_member(self, col, cell, model, iter):
        member = model.get_value(iter, 1)
        cell.set_property('text', repr(member))

    def __close_cb(self, action):
        self.__handle_close()

    def __handle_close(self):
        _logger.debug("got close")
        if self.__filename:
            self.__idle_save_text()
        self.destroy()

    def __create_ui(self):
        self.__actiongroup = ag = gtk.ActionGroup('WindowActions')
        actions = [
            ('FileMenu', None, _('_File')),
            ('Close', gtk.STOCK_CLOSE, _('_Close'), '<control>Return', _('Hide window'), self.__close_cb),
            ]
        ag.add_actions(actions)
        self._ui = gtk.UIManager()
        self._ui.insert_action_group(ag, 0)
        self._ui.add_ui_from_string(self.__ui_string)
        self.add_accel_group(self._ui.get_accel_group())
