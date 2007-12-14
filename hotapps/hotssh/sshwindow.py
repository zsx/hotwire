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

_logger = logging.getLogger("hotssh.SshWindow")

_CONTROLPATH = None
def get_controlpath():
    global _CONTROLPATH
    if _CONTROLPATH is None:
        _CONTROLPATH = tempfile.mkdtemp('', 'hotssh')
    return _CONTROLPATH

# TODO - openssh should really do this out of the box
def get_sshcmd():
    return ['ssh', '-oControlMaster=auto', '-oControlPath=' + os.path.join(get_controlpath(), 'master-%r@%h:%p')]

class HostConnectionMonitor(gobject.GObject):
    __gsignals__ = {
        "host-status" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,gobject.TYPE_BOOLEAN,gobject.TYPE_PYOBJECT)),
    }      
    def __init__(self):
        super(HostConnectionMonitor, self).__init__()
        self.__host_monitor_ids = {}
        self.__check_statuses = {}
    
    def start_monitor(self, host):
        if not (host in self.__host_monitor_ids or host in self.__check_statuses):
            _logger.debug("adding monitor for %s", host)            
            self.__host_monitor_ids[host] = gobject.timeout_add(700, self.__check_host, host)
            
    def stop_monitor(self, host):
        _logger.debug("stopping monitor for %s", host)
        if host in self.__host_monitor_ids:
            monid = self.__host_monitor_ids[host]
            gobject.source_remove(monid)
            del self.__host_monitor_ids[host]
        if host in self.__check_statuses:
            del self.__check_statuses[host]
        
    def get_monitors(self):
        return self.__host_monitor_ids
            
    def __check_host(self, host):
        _logger.debug("performing check for %s", host)
        del self.__host_monitor_ids[host]
        cmd = list(get_sshcmd())
        starttime = time.time()
        # This is a hack.  Blame Adam Jackson.
        cmd.extend(['-oBatchMode=true', host, '/bin/true'])
        subproc = subprocess.Popen(cmd)
        child_watch_id = gobject.child_watch_add(subproc.pid, self.__on_check_exited, host)
        timeout_id = gobject.timeout_add(7000, self.__check_timeout, host)
        self.__check_statuses[host] = (starttime, subproc.pid, timeout_id, child_watch_id)
        return False
        
    def __check_timeout(self, host):
        _logger.debug("timeout for host=%s", host)
        try:
            (starttime, pid, timeout_id, child_watch_id) = self.__check_statuses[host]
        except KeyError, e:
            return False
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError, e:
            _logger.debug("failed to signal pid %s", pid, exc_info=True)
            pass
        return False    
        
    def __on_check_exited(self, pid, condition, host):
        _logger.debug("check exited, pid=%s condition=%s host=%s", pid, condition, host)
        try:
            (starttime, pid, timeout_id, child_watch_id) = self.__check_statuses[host]
        except KeyError, e:
            return False
        gobject.source_remove(timeout_id)
        del self.__check_statuses[host]    
        self.__host_monitor_ids[host] = gobject.timeout_add(4000, self.__check_host, host)              
        self.emit('host-status', host, condition == 0, time.time()-starttime)
        return False
        
_hostmonitor = HostConnectionMonitor()

class SshTerminalWidget(gtk.VBox):
    def __init__(self, args, cwd):
        super(SshTerminalWidget, self).__init__()
        self.__connecting_state = False
        self.__connected = None
        self.__latency = None
        self.__sshcmd = list(get_sshcmd())
        self.__sshcmd.extend(args)
        self.__cwd = cwd
        self.__host = None
        self.__sshopts = []
        for arg in args:
            if not arg.startswith('-'):
                if self.__host is None:                 
                    self.__host = arg
            else:
                self.__sshopts.append(arg)
                
        header = gtk.HBox()
        self.__msg = gtk.Label()
        self.__msg.set_alignment(0.0, 0.5)
        header.pack_start(self.__msg)
        self.pack_start(header, expand=False)
        self.connect()
        
    def set_status(self, connected, latency):
        if not connected and self.__connecting_state:
            return
        self.__connecting_state = False
        connected_changed = self.__connected != connected
        latency_changed = (not self.__latency) or (self.__latency*0.9 > latency) or (self.__latency*1.1 < latency)
        if not (connected_changed or latency_changed):
            return        
        self.__connected = connected
        self.__latency = latency
        self.__sync_msg()
        
    def __sync_msg(self):
        if self.__connecting_state:
            text = 'Connecting'
        elif self.__connected is True:
            text = 'Connected (%.2fs latency)' % (self.__latency)
        elif self.__connected is False:
            text = '<span foreground="red">Disconnected</span>'
        elif self.__connected is None:
            text = 'Checking connection'
        if len(self.__sshopts) > 1:
            text += '; Options: ' + (' '.join(map(gobject.markup_escape_text, self.__sshopts)))
        self.__msg.set_markup(text)
        
    def connect(self):
        self.__connecting_state = True        
        self.__term = term = VteTerminalWidget(cwd=self.__cwd, cmd=self.__sshcmd)
        term.connect('child-exited', self.__on_child_exited)
        term.show_all()
        self.pack_start(term, expand=True)
        self.__sync_msg()
        
    def reconnect(self):
        # TODO - do this in a better way
        if not self.__term.exited:
            os.kill(self.__term.pid, signal.SIGTERM)
        self.remove(self.__term)
        self.__term.destroy()
        self.connect()    
        
    def __on_child_exited(self, term):
        _logger.debug("disconnected")
        self.__msg.set_text('Disconnected')
        
    def get_vte(self):
        return self.__term.get_vte()
        
    def get_title(self):
        return self.get_host()
    
    def get_host(self):
        return self.__host
    
    def get_options(self):
        return self.__sshopts

class SshWindow(VteWindow):
    def __init__(self, **kwargs):
        super(SshWindow, self).__init__(title='HotSSH', icon_name='openssh', **kwargs)
        
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <placeholder name='FileAdditions'>
        <menuitem action='CopyConnection'/>    
        <menuitem action='OpenSFTP'/>
      </placeholder>
    </menu>
    <placeholder name='TermAppAdditions'>
      <menu action='ConnectionMenu'>
        <menuitem action='Reconnect'/>
      </menu>
    </placeholder>
  </menubar>
</ui>
"""       

        self._get_notebook().connect('switch-page', self.__on_page_switch)

        try:
            self.__nm_proxy = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
            self.__nm_proxy.connect_to_signal('StateChange', self.__on_nm_state_change)
        except dbus.DBusException, e:
            _logger.debug("Couldn't find NetworkManager")
            self.__nm_proxy = None
        
        self.connect("notify::is-active", self.__on_is_active_changed)
        _hostmonitor.connect('host-status', self.__on_host_status)
        
        self.__merge_ssh_ui()
        
    def new_tab(self, args, cwd):
        term = SshTerminalWidget(args=args, cwd=cwd)
        self.append_widget(term)
        
    def __on_nm_state_change(self, *args):
        self.__sync_nm_state()
        
    def __sync_nm_state(self):
        self.__nm_proxy.GetActiveConnections(reply_handler=self.__on_nm_connections, error_handler=self.__on_dbus_error)
        
    def __on_nm_connections(self, connections):
        _logger.debug("nm connections: %s", connections)    
        
    def __on_host_status(self, hostmon, host, connected, latency):
        _logger.debug("got host status host=%s conn=%s latency=%s", host, connected, latency)
        for widget in self._get_notebook().get_children():
            child_host = widget.get_host()
            if child_host != host:
                continue
            widget.set_status(connected, latency)
            
    def __on_is_active_changed(self, *args):
        isactive = self.get_property('is-active')
        if isactive:
            self.__start_monitoring()
        else:
            self.__stop_monitoring()
        
    def __on_page_switch(self, n, p, pn):
        # Becuase of the way get_current_page() works in this signal handler, this
        # will actually disable monitoring for the previous tab, and enable it
        # for the new current one.
        self.__stop_monitoring()
        self.__start_monitoring(pn=pn)
            
    def __stop_monitoring(self):
        notebook = self._get_notebook()
        pn = notebook.get_current_page()
        if pn >= 0:
            prev_widget = notebook.get_nth_page(pn)
            prev_host = prev_widget.get_host()
            _hostmonitor.stop_monitor(prev_host)
            prev_widget.set_status(None, None)        
            
    def __start_monitoring(self, pn=None):
        notebook = self._get_notebook()
        if pn is not None:
            pagenum = pn
        else:
            pagenum = notebook.get_current_page()
        widget = notebook.get_nth_page(pagenum)
        _hostmonitor.start_monitor(widget.get_host())
        
    def __merge_ssh_ui(self):
        self.__using_accels = True
        self.__actions = actions = [
            ('CopyConnection', gtk.STOCK_NEW, 'New tab for connection', '<control><shift>t',
             'Open a new tab for the same remote computer', self.__copy_connection_cb),              
            ('OpenSFTP', gtk.STOCK_NEW, 'Open SFTP', None,
             'Open a SFTP connection', self.__open_sftp_cb),            
            ('ConnectionMenu', None, 'Connection'),
            ('Reconnect', None, '_Reconnect', None, 'Reset connection to server', self.__reconnect_cb),
            ]
        self._merge_ui(self.__actions, self.__ui_string)
        
    def __copy_connection_cb(self, action):
        notebook = self._get_notebook()
        widget = notebook.get_nth_page(notebook.get_current_page())
        host = widget.get_host()
        opts = widget.get_options()
        args = list(opts)
        args.append(host)
        self.new_tab(args, None)
        
    def __open_sftp_cb(self, action):
        notebook = self._get_notebook()        
        widget = notebook.get_nth_page(notebook.get_current_page())
        host = widget.get_host()
        subprocess.Popen(['nautilus', 'sftp://%s' % (host,)])
        
    def __reconnect_cb(self, a):
        notebook = self._get_notebook()        
        widget = notebook.get_nth_page(notebook.get_current_page())
        widget.reconnect()

class SshApp(VteApp):
    def __init__(self):
        super(SshApp, self).__init__('HotSSH', SshWindow)
                
    def on_shutdown(self, factory):
        cp = get_controlpath()
        try:
            _logger.debug("removing %s", cp)
            shutil.rmtree(cp)
        except:
            pass
