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

import os,sys,platform,logging,getopt
import locale,threading,subprocess,time
import signal,tempfile,shutil

import gtk,gobject,pango
import dbus,dbus.glib,dbus.service

from hotvte.vteterm import VteTerminalWidget
from hotvte.vtewindow import VteWindow
from hotvte.vtewindow import VteApp

_logger = logging.getLogger("hotsudo.SudoWindow")

class AnimatedBorderBox(gtk.Bin):
    def __init__(self, color, width):
        super(AnimatedBorderBox, self).__init__()
        self.__animate_id = 0
        self.color = color
        self.width = width
        
    def do_expose(self, event):
        flags = self.get_flags()
        if (flags & gtk.VISIBLE) and (flags & gtk.MAPPED):
            self.paint(event.area)
        return False 
    
    def do_size_request(self, req):
        req.width = 0
        req.height = 0
        if self.child and (self.child.get_flags() & gtk.VISIBLE):
            child_req = child.size_request()
            req.width = child_req.width
            req.height = child_req.height
            
        req.width += self.border_width + self.style.xthickness * 2;
        req.height += self.border_width + self.style.ythickness * 2;
        
    def do_size_allocate(self, alloc):
        self.allocation = alloc
        childalloc = self.__get_child_alloc()
        
    def __get_child_alloc(self):
        topmargin = self.style.ythickness
        x = self.border_width + self.style.xthickness
        width = max(1, self.allocation.width - x*2)
        y = self.border_width + topmargin
        height = max(1, self.allocation.height - y - self.border_width - self.style.ythickness)
        x += self.allocation.x
        y += self.allocation.y
        return (x,y,width,height)

class SudoTerminalWidget(gtk.VBox):
    def __init__(self, args, cwd):
        super(SudoTerminalWidget, self).__init__()
        self.__cmd = ['sudo']
        self.__cmd.extend(args)
        self.__cwd = cwd
        _logger.debug("creating vte, cmd=%s cwd=%s", self.__cmd, cwd)
        self.__term = term = VteTerminalWidget(cmd=self.__cmd, cwd=cwd)
        term.connect('child-exited', self.__on_child_exited)
        term.show_all()
        self.__headerbox = gtk.HBox()
        self.pack_start(self.__headerbox, expand=False)
        self.pack_start(term, expand=True)
        
    def __on_child_exited(self, term):
        _logger.debug("disconnected")
        msg = gtk.Label('Command exited')
        msg.set_alignment(0.0, 0.5)
        self.__headerbox.pack_start(msg)
        self.__headerbox.show_all()
        
    def get_vte(self):
        return self.__term.get_vte()
        
    def get_title(self):
        return ' '.join(self.__cmd)
    
    def get_cwd(self):
        return self.__cwd

class SudoWindow(VteWindow):
    def __init__(self, **kwargs):
        super(SudoWindow, self).__init__(title='HotSudo', icon_name='sudo', **kwargs)
        
        self.__default_args = ['su', '-']
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <placeholder name='FileAdditions'>
        <menuitem action='NewTabShell'/>
      </placeholder>
    </menu>
  </menubar>
</ui>
"""
        self.__merge_sudo_ui()
        
    def new_tab(self, args, cwd):
        if not args:
            args = self.__default_args
        term = SudoTerminalWidget(args=args, cwd=cwd)
        self.append_widget(term)
        
    def __merge_sudo_ui(self):
        self.__using_accels = True
        self.__actions = actions = [
            ('NewTabShell', gtk.STOCK_NEW, 'New shell tab', '<control><shift>t',
             'Open a new tab with a shell', self.__new_tab_shell_cb),
            ]
        self._merge_ui(self.__actions, self.__ui_string)
        
    def __new_tab_shell_cb(self, action):
        notebook = self._get_notebook()
        widget = notebook.get_nth_page(notebook.get_current_page())
        cwd = widget.get_cwd()
        self.new_tab(self.__default_args, cwd=cwd)

class SudoApp(VteApp):
    def __init__(self):
        super(SudoApp, self).__init__('HotSudo', SudoWindow)
