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

from hotwire.command import Pipeline,Command,HotwireContext
from hotwire.completion import Completion, VerbCompleter, TokenCompleter
import hotwire.command
import hotwire.version
import hotwire_ui.widgets as hotwidgets
import hotwire_ui.pyshell
from hotwire.externals.singletonmixin import Singleton
from hotwire.sysdep.term import Terminal
from hotwire.builtin import BuiltinRegistry
from hotwire.cmdalias import Alias, AliasRegistry
from hotwire.gutil import *
from hotwire.util import markup_for_match, quote_arg
from hotwire.fs import path_unexpanduser, path_expanduser, unix_basename, path_fromurl
from hotwire.sysdep import is_unix
from hotwire.sysdep.fs import File, Filesystem
from hotwire.state import History, Preferences
from hotwire_ui.command import CommandExecutionDisplay,CommandExecutionControl
from hotwire_ui.completion import CompletionStatusDisplay
from hotwire_ui.prefs import PrefsWindow
from hotwire_ui.dirswitch import DirSwitchWindow
from hotwire.logutil import log_except
from hotwire.externals.dispatch import dispatcher

_logger = logging.getLogger("hotwire.ui.Shell")

def locate_current_window(widget):
    """A function which can be called from any internal widget to gain a reference
    to the toplevel Hotwire window container."""
    win = widget.get_toplevel()
    return win

def locate_current_shell(widget):
    """A function which can be called from any internal widget to gain a reference
    to the toplevel Hotwire instance."""
    win = locate_current_window(widget)
    return win.get_current_widget()

class HotwireClientContext(hotwire.command.HotwireContext):
    def __init__(self, hotwire, **kwargs):
        super(HotwireClientContext, self).__init__(**kwargs)
        self.__hotwire = hotwire
        self.history = None

    def do_cd(self, dpath):
        self.__hotwire.internal_execute('cd', dpath)
        
    def get_gtk_event_time(self):
        return gtk.get_current_event_time()

    def push_msg(self, text, **kwargs):
        self.__hotwire.push_msg(text, **kwargs)

    def get_current_output_type(self):
        return self.__hotwire.get_current_output_type()

    def get_current_output(self):
        return self.__hotwire.get_current_output()

    def get_history(self):
        # FIXME arbitrary limit
        return self.history.search_commands(None, limit=250)

    def ssh(self, host):
        self.__hotwire.ssh(host)

    def remote_exit(self):
        self.__hotwire.remote_exit()

    def open_term(self, cwd, pipeline, arg, window=False):
        gobject.idle_add(self.__idle_open_term, cwd, pipeline, arg, window)

    def open_pyshell(self):
        gobject.idle_add(self.__idle_open_pyshell)

    def __idle_open_term(self, cwd, pipeline, arg, do_window):
        title = str(pipeline)
        window = locate_current_window(self.__hotwire)
        term = Terminal.getInstance().get_terminal_widget_cmd(cwd, arg, title)
        if do_window:
            window.new_win_widget(term, title)
        else:
            window.new_tab_widget(term, title)
        
    def __idle_open_pyshell(self):
        self.__hotwire.open_pyshell()
    
    def get_ui(self):
        return self.__hotwire.get_global_ui()

class Hotwire(gtk.VBox):
    MAX_RECENTDIR_LEN = 10
    __gsignals__ = {
        "title" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        "new-tab-widget" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_STRING)),
        "new-window-cmd" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))        
    }
    MAX_TABHISTORY = 30
    def __init__(self, initcwd=None, window=None, ui=None, initcmd_widget=None, initcmd=None):
        super(Hotwire, self).__init__()

        _logger.debug("Creating Hotwire instance, initcwd=%s", initcwd)

        self.__ui = ui
        
        self.__ui_string = '''
<ui>
  <menubar name='Menubar'>
    <placeholder name='WidgetMenuAdditions'>  
      <menu action='GoMenu'>
        <menuitem action='Up'/>
        <menuitem action='Back'/>
        <menuitem action='Forward'/>
        <separator/>              
        <menuitem action='DirSwitch'/>
        <separator/>
        <menuitem action='AddBookmark'/>
        <separator/>
        <menuitem action='Home'/>
      </menu>
    </placeholder>
  </menubar>
</ui>'''
        self.__actions = [
            ('GoMenu', None, _('_Go')),
            ('Up', 'gtk-go-up', _('Up'), '<alt>Up', _('Go to parent directory'), self.__up_cb),
            ('Back', 'gtk-go-back', _('Back'), '<alt>Left', _('Go to previous directory'), self.__back_cb),
            ('Forward', 'gtk-go-forward', _('Forward'), '<alt>Right', _('Go to next directory'), self.__forward_cb),
            ('AddBookmark', None, _('Add Bookmark'), '<alt><shift>B', _('Set a bookmark at this directory'), self.__add_bookmark_cb),
            ('Home', 'gtk-home', _('_Home'), '<alt>Home', _('Go to home directory'), self.__home_cb),
            ('DirSwitch', 'gtk-find', _('Quick Switch'), '<alt>Down', _('Search for a directory'), self.__dirswitch_cb)
        ]
        self.__action_group = gtk.ActionGroup('HotwireActions')
        self.__action_group.add_actions(self.__actions)

        self.context = HotwireClientContext(self, initcwd=initcwd)
        self.context.history = History.getInstance()
        self.__tabhistory = []
        self.context.connect("cwd", self.__on_cwd)

        self.__cwd = self.context.get_cwd()
        
        bookmarks = Filesystem.getInstance().get_bookmarks()
        dispatcher.connect(self.__handle_bookmark_change, sender=bookmarks)
        gobject.idle_add(self.__sync_bookmarks)

        self.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP,
                           [('text/uri-list', 0, 0)],
                           gtk.gdk.ACTION_COPY) 
        self.connect("drag-data-received", self.__on_drag_data_received)
        self.connect("key-press-event", self.__on_toplevel_keypress) 

        self.__paned = gtk.VBox()
        self.__topbox = gtk.VBox()
        self.__welcome = gtk.Label('Welcome to Hotwire.')
        self.__welcome_align = hotwidgets.Align(self.__welcome, yscale=1.0, xscale=1.0)
        self.__paned.pack_start(self.__welcome_align, expand=True)
        self.pack_start(self.__paned, expand=True)

        self.__outputs = CommandExecutionControl(self.context)
        self.__outputs.connect("new-window", self.__on_commands_new_window)        
        self.__topbox.pack_start(self.__outputs, expand=True)

        self.__bottom = gtk.VBox()
        self.__paned.pack_end(hotwidgets.Align(self.__bottom, xscale=1.0, yalign=1.0), expand=False)

        self.__msgline = gtk.Label('')
        self.__msgline.set_selectable(True)
        self.__msgline.set_ellipsize(True)
        self.__msgline.unset_flags(gtk.CAN_FOCUS)
        self.__bottom.pack_start(hotwidgets.Align(self.__msgline), expand=False)

        self.__emacs_bindings = None
        self.__active_input_completers = []
        self.__input = gtk.Entry()
        self.__input.connect("notify::scroll-offset", self.__on_scroll_offset)
        self.__input.connect("notify::text", lambda *args: self.__on_input_changed())
        self.__input.connect("key-press-event", lambda i, e: self.__on_input_keypress(e))
        self.__input.connect("focus-out-event", self.__on_entry_focus_lost)
        self.__bottom.pack_start(self.__input, expand=False)

        self.__statusbox = gtk.VBox()
        self.__bottom.pack_start(self.__statusbox, expand=False)

        self.__statusline = gtk.HBox()
        self.__statusbox.pack_start(hotwidgets.Align(self.__statusline), expand=False)
        self.__doing_recentdir_sync = False
        self.__doing_recentdir_navigation = False
        self.__recentdir_navigation_index = None
        self.__recentdirs = gtk.combo_box_new_text()
        self.__recentdirs.set_focus_on_click(False)
        self.__recentdirs.connect('changed', self.__on_recentdir_selected)
        self.__statusline.pack_start(hotwidgets.Align(self.__recentdirs), expand=False)
        
        def create_arrow_button(action_name):
            action = self.__action_group.get_action(action_name)
            icon = action.create_icon(gtk.ICON_SIZE_MENU)
            button = gtk.Button(label=action.get_property('label'))
            button.connect('clicked', lambda *args: action.activate())
            def on_action_sensitive(a, p):
                button.set_sensitive(action.get_sensitive())
            action.connect("notify::sensitive", on_action_sensitive)
            # There is some bug here causing the GC of on_action_sensitive; avoid it
            # by attaching a ref to button
            button.x = on_action_sensitive
            button.set_property('image', icon)
            button.set_focus_on_click(False)
            return button
        sizegroup = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        back = create_arrow_button('Back')
        sizegroup.add_widget(back)
        self.__statusline.pack_start(back, expand=False)       
        fwd = create_arrow_button('Forward')
        sizegroup.add_widget(fwd)
        self.__statusline.pack_start(fwd, expand=False)
        up = create_arrow_button('Up')
        sizegroup.add_widget(up)
        self.__statusline.pack_start(up, expand=False)        

        self.__idle_parse_id = 0
        self.__parse_stale = False
        self.__meta_syntax = None
        self.__parsed_pipeline = None
        self.__verb_completer = VerbCompleter()
        self.__token_completer = TokenCompleter()
        self.__completion_active = False
        self.__completion_active_position = False
        self.__completion_chosen = None
        self.__completion_suppress = False
        self.__completion_async_blocking = False
        self.__completions = CompletionStatusDisplay(self.__input, window, context=self.context,
                                                     tabhistory=self.__tabhistory)
        self.__completions.connect('completion-selected', self.__on_completion_selected)
        self.__completions.connect('completions-loaded', self.__on_completions_loaded)
        self.__completions.connect('histitem-selected', self.__on_histitem_selected)
        self.__completion_token = None
        self.__history_suppress = False
        self.__history_search_saved = None
        self.__history_search_active = False

        self.__sync_cwd()
        self.__update_status()

        prefs = Preferences.getInstance()
        prefs.monitor_prefs('ui.', self.__on_pref_changed)
        self.__sync_prefs(prefs)

        if initcmd_widget:
            self.__unset_welcome()            
            self.__outputs.add_cmd_widget(initcmd_widget)
        elif initcmd:
            gobject.idle_add(lambda: self.execute_pipeline(Pipeline.parse(initcmd, self.context), add_history=False, reset_input=False))

    def get_global_ui(self):
        return self.__ui

    def get_ui_pairs(self):
        return [self.__outputs.get_ui(), (self.__ui_string, self.__action_group)]

    def open_pyshell(self):
        PYCMD_CONTENT = '''## Python Command
import os,sys,re
import gtk, gobject

# input type: %s
for obj in curshell.get_current_output():
  ''' % (self.get_current_output_type(),)
        shell = hotwire_ui.pyshell.CommandShell({'curshell': self},
                                                content=PYCMD_CONTENT)
        shell.set_icon_name('hotwire')        
        shell.set_title(_('Hotwire Python Command'))
        shell.show_all()  

    def append_tab(self, widget, title):
        self.emit("new-tab-widget", widget, title)

    def push_msg(self, msg, markup=False):
        if not markup:
            self.__msgline.set_text(msg)
        else:
            self.__msgline.set_markup(msg)
            
    def __add_bookmark_cb(self, action):
        bookmarks = Filesystem.getInstance().get_bookmarks()
        bookmarks.add(self.__cwd)
            
    def __handle_bookmark_change(self, signal=None, sender=None):
        self.__sync_bookmarks()
        
    def __sync_bookmarks(self):
        gomenu = self.__ui.get_widget('/Menubar/WidgetMenuAdditions/GoMenu/Home').get_parent()
        removals = []
        for child in gomenu:
            if child.get_data('hotwire-dynmenu'):
                removals.append(child)
                
        for removal in removals:
            gomenu.remove(removal)
            
        for bookmark in Filesystem.getInstance().get_bookmarks():
            bn = unix_basename(bookmark)
            menuitem = gtk.ImageMenuItem(bn)
            menuitem.set_data('hotwire-dynmenu', True)
            menuitem.set_property('image', gtk.image_new_from_stock('gtk-directory', gtk.ICON_SIZE_MENU))
            menuitem.connect('activate', self.__on_bookmark_activate, bookmark)
            menuitem.show_all()
            gomenu.append(menuitem)
            
    def __on_bookmark_activate(self, menu, bookmark):
        self.internal_execute('cd', bookmark)

    def __sync_cwd(self):
        max_recentdir_len = self.MAX_RECENTDIR_LEN
        model = self.__recentdirs.get_model()
        if self.__doing_recentdir_navigation:
            self.__doing_recentdir_navigation = False
            _logger.debug("in recentdir navigation, setting active iter")
            iter = model.iter_nth_child(None, self.__recentdir_navigation_index)
            self.__doing_recentdir_sync = True            
            self.__recentdirs.set_active_iter(iter)
            self.__doing_recentdir_sync = False
            self.__sync_recentdir_navigation_sensitivity()            
            return
        if model.iter_n_children(None) == max_recentdir_len:
            model.remove(model.iter_nth_child(None, max_recentdir_len-1))
        unexpanded = path_unexpanduser(self.__cwd)
        model.prepend((unexpanded,))
        self.__doing_recentdir_sync = True
        self.__recentdirs.set_active(0)
        self.__doing_recentdir_sync = False
        _logger.debug("added new recentdir")
        if not self.__doing_recentdir_navigation:
            _logger.debug("reset recentdir index")                   
            self.__recentdir_navigation_index = None
        self.__sync_recentdir_navigation_sensitivity()
        
    def __sync_recentdir_navigation_sensitivity(self):
        idx = self.__recentdir_navigation_index        
        self.__action_group.get_action('Forward').set_sensitive(idx is not None and idx > 0)
        n_total = self.__recentdirs.get_model().iter_n_children(None)
        self.__action_group.get_action('Back').set_sensitive((idx is None and n_total > 1) or (idx is not None and idx < n_total-1))
        bookmarkable = self.__cwd != path_expanduser("~") and self.__cwd not in Filesystem.getInstance().get_bookmarks()
        self.__action_group.get_action('AddBookmark').set_sensitive(bookmarkable)

    def __up_cb(self, action):
        _logger.debug("up")
        self.execute_internal_str("cd ..")
        
    @log_except(_logger)
    def __dirswitch_cb(self, action):
        _logger.debug("doing dirswitch")
        win = DirSwitchWindow()
        dirpath = win.run_get_value()
        if not dirpath:
            return
        self.internal_execute('cd', dirpath)
        
    def __do_recentdir_cd(self):
        model = self.__recentdirs.get_model()
        iter = model.iter_nth_child(None, self.__recentdir_navigation_index)
        path = path_expanduser(model.get_value(iter, 0))
        self.__doing_recentdir_navigation = True
        self.internal_execute('cd', path)            

    def __back_cb(self, action):
        _logger.debug("back")
        if self.__recentdir_navigation_index is None:
            self.__recentdir_navigation_index = 0
        self.__recentdir_navigation_index += 1
        self.__do_recentdir_cd()        

    def __forward_cb(self, action):
        _logger.debug("forward")
        assert(self.__recentdir_navigation_index is not None)
        self.__recentdir_navigation_index -= 1
        self.__do_recentdir_cd()   

    def __home_cb(self, action):
        _logger.debug("home")
        self.execute_internal_str('cd')

    def __on_commands_new_window(self, outputs, cmdview):
        _logger.debug("got new window request for %s", cmdview)
        self.emit('new-window-cmd', cmdview)

    @defer_idle_func(timeout=0) # commands can invoke the cwd signal from a thread context
    def __on_cwd(self, ctx, cwd):
        self.__cwd = cwd
        self.__sync_cwd()
        self.__update_status()

    def __on_recentdir_selected(self, *args):
        if self.__doing_recentdir_sync:
            return
        iter = self.__recentdirs.get_active_iter()
        d = self.__recentdirs.get_model().get_value(iter, 0)
        _logger.debug("selected recent dir %s", d)
        self.context.do_cd(d)        

    def get_current_output_type(self):
        odisp = self.__outputs.get_current()
        if not odisp:
            return None
        return odisp.get_pipeline().get_output_type()
    
    def get_current_output(self):
        odisp = self.__outputs.get_current()
        if not odisp:
            return None
        return odisp.get_objects()        
    
    def do_copy_url_drag_to_dir(self, urls, path):
        def fstrip(url):
            if url.startswith('file://'):
                return url[7:]
            return url
        fpaths = map(fstrip, urls.split('\r\n'))
        _logger.debug("path is %s, got drop paths: %s", path, quoted_fpaths)
        fpaths.append(path)
        self.internal_execute('cp', *fpaths)
    
    def __on_drag_data_received(self, tv, context, x, y, selection, info, etime):
        sel_data = selection.data
        self.do_copy_url_drag_to_dir(sel_data, self.context.get_cwd())
        
    def get_entry(self):
        return self.__input
    
    def grab_focus(self):
        self.__input.grab_focus()
        
    def completions_hide(self):
        self.__completions.hide_all()

    def __update_status(self):
        self.emit("title", self.get_title())

    def get_title(self):
        cwd = self.context.get_cwd()
        return unix_basename(cwd)

    def append_text(self, text):
        curtext = self.__input.get_property('text')
        if curtext and curtext[-1] != ' ':
            text = ' ' + text
        self.__input.set_property('text', curtext + text)

    def internal_execute(self, *args):
        pipeline = Pipeline.create(self.context, None, *args)
        self.execute_pipeline(pipeline, add_history=False, reset_input=False)        

    def execute_pipeline(self, pipeline,
                            add_history=True,
                            reset_input=True,
                            tree=None):
        _logger.debug("pipeline: %s", pipeline)

        if pipeline.is_nostatus():
            pipeline.execute_sync()

        if add_history:
            text = self.__input.get_property("text").strip()
            self.context.history.append_command(text, self.context.get_cwd())
            if tree:
                History.getInstance().record_pipeline(self.__cwd, self.__parsed_pipeline)
            self.__tabhistory.insert(0, text)
            if len(self.__tabhistory) >= self.MAX_TABHISTORY:
                self.__tabhistory.pop(-1)
        if reset_input:
            self.__input.set_text("")
            self.__completion_token = None
            self.__completions.invalidate()

        self.__update_status()

        if pipeline.is_nostatus():
            return

        self.__unset_welcome()

        self.__outputs.add_pipeline(pipeline)
        pipeline.execute(opt_formats=self.__outputs.get_current().get_opt_formats())
        
    def __unset_welcome(self):
        if not self.__welcome:
            return
        self.__paned.remove(self.__welcome_align)
        self.__paned.pack_end(self.__topbox, expand=True)
        self.__topbox.show_all()
        self.__welcome = None
        self.__welcome_align = None        

    def __execute(self):
        self.__completions.hide_all()
        if self.__parse_stale:
            try:
                self.__do_parse(throw=True)
            except hotwire.command.PipelineParseException, e:
                if self.__meta_syntax is None:
                    self.push_msg(_("Failed to parse pipeline: %s") % (e.args[0],))
                    return
                
        text = self.__input.get_property("text")

        if self.__meta_syntax == 'sh':
            _logger.debug("using sh meta syntax")
            pipeline = Pipeline.create(self.context, None,
                                       'sys', '/bin/sh', '-c', text[3:])
            self.execute_pipeline(pipeline)
            return
        else:
            assert self.__meta_syntax is None
                
        _logger.debug("executing '%s'", self.__parsed_pipeline)
        if not self.__parsed_pipeline:
            _logger.debug("Nothing to execute")
            return

        # clear message if any
        self.push_msg('')

        resolutions = []
        vc = self.__verb_completer
        fs = Filesystem.getInstance()
        
        def resolver(text):
            resolution_match = None
            for completion in vc.completions(text, self.__cwd):
                target = completion.target
                if isinstance(target, Alias) and text == target.name:
                    resolution_match = completion
                    break
                if isinstance(target, File) and \
                   not target.is_directory() and \
                   (unix_basename(text) == unix_basename(target.path) or fs.path_inexact_executable_match(completion.matchbase)):
                    resolution_match = completion
                    break
            _logger.debug("resolution match is %s", resolution_match)                
            if resolution_match:
                if isinstance(resolution_match.target, Alias):
                    tokens = list(Pipeline.tokenize(resolution_match.target.target))                   
                    return (BuiltinRegistry.getInstance()[tokens[0].text], tokens[1:])               
                elif isinstance(resolution_match.target, File):
                    return (BuiltinRegistry.getInstance()['sys'], [resolution_match.target.path])
            return (None, None)
        
        self.__parsed_pipeline = Pipeline.parse(text, context=self.context, resolver=resolver)
        self.execute_pipeline(self.__parsed_pipeline)

    @log_except(_logger)
    def __on_histitem_selected(self, popup, histitem):
        _logger.debug("got history item selected: %s", histitem)
        if not histitem:
            _logger.debug("no history item, doing popdown")
            self.__completions.hide_all()
            return
        self.__input.set_text(histitem)
        self.__input.set_position(-1)

    @log_except(_logger)
    def __on_completion_selected(self, popup, completion):
        _logger.debug("got completion selected")
        if not completion:
            _logger.debug("no completion, doing popdown")
            self.__completions.hide_all()
            return
        self.__insert_single_completion(completion)

    def __on_completions_loaded(self, compls):
        assert self.__completion_async_blocking
        _logger.debug("completions loaded")        
        self.__insert_completion()

    def __do_completion(self):
        _logger.debug("requesting completion")
        if self.__parse_stale:
            try:
                self.__do_parse(throw=True)
            except hotwire.command.PipelineParseException, e:
                self.push_msg('Failed to parse pipeline: %s' % (e.args[0],))
                return
            self.__do_complete()
        self.__insert_completion()
            
    def __insert_single_completion(self, completion):
        text = completion.suffix
        # FIXME move this into CompletionSystem
        tobj = completion.target
        if not (isinstance(tobj, File) and tobj.is_directory()):
            text += " "
        self.__insert_completing_text(text)
            
    def __insert_completing_text(self, text):
        curtext = self.__input.get_property("text")        
        pos = self.__input.get_position()
        self.__completion_suppress = True
        self.__input.set_property('text', curtext + text)
        self.__input.set_position(pos + len(text))
        self.__completion_suppress = False
        self.__parse_stale = True
        self.__completions.invalidate()
        self.__completions.hide_all()
        self.__queue_parse()           
            
    def __insert_completion(self):
        results = self.__completions.completion_request()
        if results is None:
            self.__completion_async_blocking = True
            _logger.debug("results pending, setting blocking=TRUE")
            self.__completions.hide_all()            
            return
        if self.__completion_async_blocking:
            _logger.debug("setting blocking=FALSE")            
            self.__completion_async_blocking = False
        if len(results.results) == 0:
            _logger.debug("no completions")
            return
        if len(results.results) == 1:
            _logger.debug("single completion: %r", results.results[0])            
            self.__insert_single_completion(results.results[0])
        elif results.common_prefix:
            _logger.debug("completion common prefix: %r", results.common_prefix)
            self.__insert_completing_text(results.common_prefix)
        else:
            # We should have popped up the display list
            pass

    def __handle_completion_key(self, e):
        curtext = self.__input.get_property("text")
        state = self.__completions.get_state()
        if (state is not None) and e.keyval == gtk.gdk.keyval_from_name('Return'):
            self.__completions.activate_selected()
            return True         
        elif e.keyval == gtk.gdk.keyval_from_name('Tab'):
            if curtext:
                self.__do_completion()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('r') and e.state & gtk.gdk.CONTROL_MASK:
            self.__do_parse()            
            if state is None:
                if curtext:
                    self.__completions.popup_global_history()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Up'):
            if state is None:
                self.__completions.popup_tab_history()
            else:
                self.__completions.select_next()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Down'):
            self.__completions.select_prev()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Page_Up'):
            print >>sys.stderr, "page up"
            return self.__completions.page_up()
        elif e.keyval == gtk.gdk.keyval_from_name('Page_Down'):
            print >>sys.stderr, "page down"            
            return self.__completions.page_down()  
        elif e.keyval == gtk.gdk.keyval_from_name('Escape'):
            self.__completion_async_blocking = False
            self.__completions.hide_all()
            return True
        return False

    def __on_entry_focus_lost(self, entry, e):
        self.__completions.hide_all()
        
    @log_except(_logger)
    def __on_toplevel_keypress(self, s2, e):
        if e.keyval == gtk.gdk.keyval_from_name('Escape'):
            self.grab_focus()
            return True 
        return False       

    @log_except(_logger)
    def __on_input_keypress(self, e):
        curtext = self.__input.get_property("text")
        
        self.__requeue_parse()
        
        if self.__completion_async_blocking:
            return True

        if self.__handle_completion_key(e):
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Return'):
            self.__execute()
            return True
        elif self.__emacs_bindings and self.__handle_emacs_binding(e):
            return True     
        else:
            return False
        
    def __handle_emacs_binding(self, e):
        if e.keyval == gtk.gdk.keyval_from_name('b') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_LOGICAL_POSITIONS, -1, 0)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('f') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_LOGICAL_POSITIONS, 1, 0)
            return True        
        elif e.keyval == gtk.gdk.keyval_from_name('f') \
             and e.state & gtk.gdk.MOD1_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_WORDS, 1, False)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('b') \
             and e.state & gtk.gdk.MOD1_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_WORDS, -1, False)
            return True 
        elif e.keyval == gtk.gdk.keyval_from_name('A') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_BUFFER_ENDS, -1, True)
            return True               
        elif e.keyval == gtk.gdk.keyval_from_name('a') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_BUFFER_ENDS, -1, False)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('e') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_BUFFER_ENDS, 1, False)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('E') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('move-cursor', gtk.MOVEMENT_BUFFER_ENDS, 1, True)
            return True        
        elif e.keyval == gtk.gdk.keyval_from_name('k') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__input.emit('delete-from-cursor', gtk.DELETE_PARAGRAPH_ENDS, 1)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('d') \
             and e.state & gtk.gdk.MOD1_MASK:
            self.__input.emit('delete-from-cursor', gtk.DELETE_WORD_ENDS, 1)
            return True                       
        return False
    
    def __unqueue_parse(self):
        if self.__idle_parse_id > 0:
            gobject.source_remove(self.__idle_parse_id)
        self.__idle_parse_id = 0

    def __requeue_parse(self):
        self.__unqueue_parse()
        self.__idle_parse_id = gobject.timeout_add(450, self.__idle_do_parse_and_complete)        

    def __queue_parse(self):
        self.__parse_stale = True
        if self.__idle_parse_id > 0:
            return
        _logger.debug("queuing parse")
        self.__requeue_parse()

    def __do_parse_requeue(self):
        self.__do_parse()
        self.__requeue_parse()

    def __idle_do_parse_and_complete(self):
        self.__idle_parse_id = 0
        if not self.__parse_stale:
            return
        if not self.__do_parse():
            return
        self.__do_complete()
        
    def __do_complete(self):
        ### TODO: move more of this stuff into hotwire_ui/completion.py
        self.__completion_token = None        
        pos = self.__input.get_position()
        prev_token = None
        completer = None
        verb = None
        verbcmd = None
        addprefix = None
        # can happen when input is empty
        if not self.__parsed_pipeline:
            _logger.debug("no tree, disabling completion")
            self.__completions.invalidate()
            return
        commands = list(self.__parsed_pipeline)
        for i,cmd in enumerate(commands):
            commands[i] = list(cmd.get_tokens())
        for i,cmd in enumerate(commands):
            verb = cmd[0]
            verbcmd = self.__parsed_pipeline[i]            
            if pos >= verb.start and pos <= verb.end :
                _logger.debug("pos %r generating verb completions for '%s' (%r %r)", verb.text, pos, verb.start, verb.end)
                completer = self.__verb_completer
                self.__completion_token = verb
                break
            prev_token = verb.text
            cmdargs = cmd[1:]
            cmdlen = len(cmdargs)
            _logger.debug("not in verb, examining %d tokens for %r", cmdlen, verbcmd)
            for i,token in enumerate(cmdargs):
                if not ((pos >= token.start) and (pos <= token.end)) and not (i == cmdlen-1):
                    _logger.debug("skipping token (%s %s) out of %d: %s ", token.start, token.end, pos, token.text)
                    prev_token = token
                    continue
                _logger.debug("generating token completions from %s for '%s'", completer, token.text)
                self.__completion_token = token
                break
            if not self.__completion_token:
                _logger.debug("no completion token found, position at end")
                self.__completion_token = hotwire.command.ParsedToken('', start=pos)              
            completer = verbcmd.builtin.get_completer(self.context, cmd, i)
            if not completer:
                # This happens because of the way we auto-inject 'sys'
                if verbcmd.builtin.name == 'sys' and cmdlen == 0:
                    completer = self.__verb_completer
                else:
                    completer = self.__token_completer
        self.__completer = completer
        _logger.debug("generating completions from token: %r completer: %r", self.__completion_token, self.__completer)
        if self.__completer:
            self.__completions.set_completion(completer, self.__completion_token.text, self.context)
        else:
            _logger.debug("no valid completions found")
            self.__completions.invalidate()

    def __do_parse(self, throw=False):
        if not self.__parse_stale:
            return True
        text = self.__input.get_property("text")
        if is_unix() and text.startswith('sh '):
            self.__meta_syntax = 'sh'
        else:
            self.__meta_syntax = None 
        try:
            self.__parsed_pipeline = Pipeline.parse(text, self.context, accept_unclosed=(not throw))
        except hotwire.command.PipelineParseException, e:
            _logger.debug("parse failed, current syntax=%s", self.__meta_syntax)
            self.__parsed_pipeline = None
            if throw:
                raise e
            return False
        _logger.debug("parse tree: %s", self.__parsed_pipeline)
        self.__parse_stale = False
        self.__unqueue_parse()
        return True

    def __on_input_changed(self):
        if self.__completion_suppress:
            _logger.debug("Suppressing completion change")
            return
        self.__completions.invalidate()
        if self.__completion_active:
            self.__completion_active = False
        curvalue = self.__input.get_property("text")
        if not self.__history_suppress:
            # Change '' to None, because '' has special value to mean
            # show all history, which we don't do by default
            self.__completions.set_history_search(curvalue or None)
        self.__queue_parse()

    def __on_scroll_offset(self, i, offset):
        offset = i.get_property('scroll-offset')
        
    def __on_pref_changed(self, prefs, key, value):
        self.__sync_prefs(prefs)
        
    def __sync_prefs(self, prefs):
        _logger.debug("syncing prefs")
        emacs = prefs.get_pref('ui.emacs', default=False)
        if self.__emacs_bindings == emacs:
            return
        self.__emacs_bindings = emacs
        _logger.debug("using Emacs keys: %s", emacs)
            
class HotWindow(gtk.Window):
    ascii_nums = [long(x+ord('0')) for x in xrange(10)]

    def __init__(self, factory=None, is_initial=False, subtitle='', **kwargs):
        super(HotWindow, self).__init__()

        self.__prefs_dialog = None

        vbox = gtk.VBox()
        self.add(vbox)
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <menuitem action='NewWindow'/>
      <menuitem action='NewTab'/>
      <menuitem action='NewTermTab'/>
      <separator/>
      <menuitem action='DetachTab'/>
      <placeholder name='FileDetachAdditions'>
      </placeholder>
      <separator/>
      <menuitem action='Close'/>
    </menu>
    <menu action='EditMenu'>
      <placeholder name='EditMenuAdditions'/>
      <separator/>
      <menuitem action='Preferences'/>
    </menu>
    <menu action='ViewMenu'>
      <menuitem action='Fullscreen'/>
      <separator/>
    </menu>
    <placeholder name='WidgetMenuAdditions'>
    </placeholder>
    <menu action='ToolsMenu'>
      <menuitem action='PythonWorkpad'/>
      <separator/>
      <menuitem action='HelpCommand'/>      
      <menuitem action='About'/>
    </menu>
  </menubar>
</ui>
"""       
        self.__create_ui()
        vbox.pack_start(self.__ui.get_widget('/Menubar'), expand=False)

        self.__pyshell = None
        self.factory = factory
        
        self.__fullscreen_mode = False

        self.__notebook = gtk.Notebook()
        self.__notebook.connect('switch-page', lambda n, p, pn: self.__focus_page(pn))
        self.__notebook.show()
        self.__tabs_visible = self.__notebook.get_show_tabs()

        self.__geom_hints = {}
        self.__old_char_width = 0
        self.__old_char_height = 0
        self.__old_geom_widget = None
        
        self.__closesigs = {}
        
        self.__curtab_is_hotwire = False

        # Records the last tab index from which we created a new tab, so we 
        # can switch back when closed, unless the user manually switched tabs
        # between.
        self.__pre_autoswitch_index = -1
        
        self.set_default_size(720, 540)
        self.set_title('Hotwire' + subtitle)
        if os.getenv("HOTWIRE_UNINSTALLED"):
            # For some reason set_icon() doesn't work even though we extend the theme path
            # do it manually.
            iinf = gtk.icon_theme_get_default().lookup_icon('hotwire', 24, 0)
            self.set_icon_from_file(iinf.get_filename())
        else:
            self.set_icon_name("hotwire")
        
        prefs = Preferences.getInstance()
        prefs.monitor_prefs('ui.', self.__on_pref_changed)
        self.__sync_prefs(prefs)

        self.connect("delete-event", lambda w, e: False)

        self.connect("key-press-event", self.__on_keypress)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.__on_buttonpress)

        vbox.add(self.__notebook)
        vbox.show()

        if 'initwidget' in kwargs:
            self.new_tab_widget(*kwargs['initwidget'])
        else:
            self.new_tab_hotwire(**kwargs)
            
    def __on_pref_changed(self, prefs, key, value):
        self.__sync_prefs(prefs)
        
    def __sync_prefs(self, prefs):
        _logger.debug("syncing prefs")
        accels = prefs.get_pref('ui.menuaccels', default=True)
        if self.__using_accels == accels:
            return
        self.__sync_action_acceleration()
        
    def __sync_action_acceleration(self):
        accels = Preferences.getInstance().get_pref('ui.menuaccels', default=True)
        self.__using_accels = accels                
        def frob_action(action):
            name = action.get_name()
            if not name.endswith('Menu'):
                return
            uiname = action.get_property('label')
            # FIXME this is gross.
            menuitem = self.__ui.get_widget('/Menubar/' + name)
            if not menuitem:
                menuitem = self.__ui.get_widget('/Menubar/WidgetMenuAdditions/' + name)
            label = menuitem.get_child()
            if accels:
                label.set_text_with_mnemonic(uiname)
            else:
                noaccel = uiname.replace('_', '')
                label.set_text(noaccel)
        for action in self.__ag.list_actions():
            frob_action(action)
        for uistr,actiongroup in self.__tab_ui_merge_ids:
            for action in actiongroup.list_actions():
                frob_action(action)                

    def get_ui(self):
        return self.__ui

    def __create_ui(self):
        self.__using_accels = True
        self.__ag = ag = gtk.ActionGroup('WindowActions')
        self.__actions = actions = [
            ('FileMenu', None, _('_File')),
            ('NewTermTab', gtk.STOCK_NEW, _('New T_erminal Tab'), '<control><shift>T',
             _('Open a new terminal tab'), self.__new_term_tab_cb),
            ('DetachTab', gtk.STOCK_JUMP_TO, _('_Detach Tab'), '<control><shift>D',
             _('Deatch current tab'), self.__detach_tab_cb),
            ('Close', gtk.STOCK_CLOSE, _('_Close'), '<control><shift>W',
             _('Close the current tab'), self.__close_cb),
            ('EditMenu', None, _('_Edit')),        
            ('ViewMenu', None, _('_View')),
            ('Preferences', gtk.STOCK_PREFERENCES, _('Preferences'), None, _('Change preferences'), self.__preferences_cb),                                       
            ('ToolsMenu', None, _('_Tools')),
            ('PythonWorkpad', 'gtk-execute', _('_Python Workpad'), '<control><shift>p', _('Launch Python evaluator'), self.__python_workpad_cb),
            ('HelpCommand', 'gtk-help', _('_Help'), None, _('Display help command'), self.__help_cb),                       
            ('About', gtk.STOCK_ABOUT, _('_About'), None, _('About Hotwire'), self.__help_about_cb),
            ]
        self.__nonterm_actions = [
            ('NewWindow', gtk.STOCK_NEW, _('_New Window'), '<control>n',
             _('Open a new window'), self.__new_window_cb),
            ('NewTab', gtk.STOCK_NEW, _('New _Tab'), '<control>t',
             _('Open a new tab'), self.__new_tab_cb)]
        self.__toggle_actions = [
            ('Fullscreen', gtk.STOCK_FULLSCREEN, _('Fullscreen'), 'F11', _('Switch to full screen mode'), self.__fullscreen_cb)
            ]
        ag.add_actions(actions)
        ag.add_actions(self.__nonterm_actions)
        ag.add_toggle_actions(self.__toggle_actions)
        self.__ui = gtk.UIManager()
        self.__ui.insert_action_group(ag, 0)
        self.__ui.add_ui_from_string(self.__ui_string)
        self.__tab_ui_merge_ids = []
        self.__ui_merge_page_id = None
        self.__nonterm_accels_installed = True
        self.add_accel_group(self.__ui.get_accel_group())       

    def __show_pyshell(self):
        if self.__pyshell:
            self.__pyshell.destroy()
        self.__pyshell = hotwire_ui.pyshell.CommandShell({'curshell': lambda: locate_current_shell(self)},
                                                         savepath=os.path.join(Filesystem.getInstance().get_conf_dir(), 'pypad.py'))
        self.__pyshell.set_icon_name('hotwire')        
        self.__pyshell.set_title(_('Hotwire PyShell'))
        self.__pyshell.show_all()      

    def __on_buttonpress(self, s2, e):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        if hasattr(widget, 'on_mouse_press'):
            if widget.on_mouse_press(e):
                return True
        return False
    
    def __get_curtab_cwd(self):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
            cwd = widget.context.get_cwd()
        else:
            cwd = os.path.expanduser('~')
        return cwd        
    
    def __new_window_cb(self, action):
        self.new_win_hotwire(initcwd=self.__get_curtab_cwd(), initcmd='ls')

    def __new_tab_cb(self, action):
        self.new_tab_hotwire(initcwd=self.__get_curtab_cwd(), initcmd='ls')

    def __new_term_tab_cb(self, action):
        self.new_tab_term(None)
        
    def __detach_tab_cb(self, action):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        title = self.__get_title(widget)
        self.__on_widget_closed(widget)
        self.new_win_widget(widget, title)

    def __close_cb(self, action):
        self.__remove_page_widget(self.__notebook.get_nth_page(self.__notebook.get_current_page()))
        
    def __fullscreen_cb(self, action):
        mode = self.__fullscreen_mode
        self.__fullscreen_mode = not self.__fullscreen_mode
        if mode:
            self.unfullscreen()
        else:
            self.fullscreen()         

    def __preferences_cb(self, action):
        if not self.__prefs_dialog:
            self.__prefs_dialog = PrefsWindow()
        self.__prefs_dialog.show_all()

    def __python_workpad_cb(self, action):
        self.__show_pyshell()
        
    def __help_cb(self, action):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
            widget.execute_internal_str('help')
        else:
            self.new_tab_hotwire(initcmd='help')

    def __help_about_cb(self, action):
        dialog = gtk.AboutDialog()
        dialog.set_property('website', 'http://hotwire-shell.org')
        dialog.set_property('version', hotwire.version.__version__)
        dialog.set_property('authors', ['Colin Walters <walters@verbum.org>'])
        dialog.set_property('copyright', u'Copyright \u00A9 2007 Colin Walters <walters@verbum.org>')
        dialog.set_property('logo-icon-name', 'hotwire')
        dialog.set_property('license', 
                            '''Hotwire is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.\n
Hotwire is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.\n
You should have received a copy of the GNU General Public License
along with Hotwire; if not, write to the Free Software Foundation, Inc.,
51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA''')
        dialog.set_property('name', "Hotwire")
        comments = _("A hypershell environment\n\n")
        if hotwire.version.svn_version_info:
            comments += "changeset: %s\ndate: %s\n" % (hotwire.version.svn_version_info['Revision'], hotwire.version.svn_version_info['Last Changed Date'],)
        dialog.set_property('comments', comments)
        dialog.run()
        dialog.destroy()

    @log_except(_logger)
    def __on_keypress(self, s2, e):
        if e.keyval == gtk.gdk.keyval_from_name('s') and \
             e.state & gtk.gdk.CONTROL_MASK and \
             e.state & gtk.gdk.MOD1_MASK:
            self.__show_pyshell()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Page_Up') and \
             e.state & gtk.gdk.CONTROL_MASK:
            idx = self.__notebook.get_current_page() 
            self.__notebook.set_current_page(idx-1)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Page_Down') and \
             e.state & gtk.gdk.CONTROL_MASK:
            idx = self.__notebook.get_current_page() 
            self.__notebook.set_current_page(idx+1)
            return True
        elif e.keyval in HotWindow.ascii_nums and \
             e.state & gtk.gdk.MOD1_MASK:
            self.__notebook.set_current_page(e.keyval-ord('0')-1) #extra -1 because tabs are 0-indexed
            return True
        return False

    @log_except(_logger)
    def __focus_page(self, pn):
        _logger.debug("got focus page, idx: %d", pn)
        # User switched tabs, reset tab affinity
        self.__preautoswitch_index = -1
        
        # Basically the entire pile of hacks below here is adapted from gnome-terminal.
        # We're actually more complex in that we have non-terminals and terminals tabs
        # in the same notebook.
        # One key hack is that we hide the widget for the non-active tab.  This seems
        # to avoid having it influence the size of the notebook when we don't want it to.
        # Note when we switch to Hotwire tabs, we set the geometry hints to nothing;
        # only terminal tabs get hints set.
        widget = self.__notebook.get_nth_page(pn)
        is_hw = widget.get_data('hotwire-is-hotwire')
        old_idx = self.__notebook.get_current_page()
        if old_idx != pn and old_idx >= 0:
            old_widget = self.__notebook.get_nth_page(old_idx)
            old_is_hw = widget.get_data('hotwire-is-hotwire')
            if hasattr(old_widget, 'hide_internals'):
                _logger.debug("hiding widget at idx %s", old_idx)
                old_widget.hide_internals()
        else:
            old_widget = None
            old_is_hw = False
        if hasattr(widget, 'show_internals'):
            _logger.debug("showing widget at idx %s", old_idx)
            widget.show_internals()            
        if is_hw:
            gobject.idle_add(self.set_focus, widget.get_entry())
            self.set_geometry_hints(widget, **{})            
            self.__old_geom_widget = widget   
        elif hasattr(widget, 'get_term_geometry'):
            (cw, ch, (xp, yp)) = widget.get_term_geometry()
            if not (cw == self.__old_char_width and ch == self.__old_char_height and widget == self.__old_geom_widget):
                _logger.debug("resetting geometry on %s %s %s => %s %s", widget, self.__old_char_width, self.__old_char_height, cw, ch)
                kwargs = {'base_width':xp,
                          'base_height':yp,
                          'width_inc':cw,
                          'height_inc':ch,
                          'min_width':xp+cw*4,
                          'min_height':yp+ch*2}
                _logger.debug("setting geom hints: %s", kwargs)
                self.__geom_hints = kwargs
                self.set_geometry_hints(widget, **kwargs)
                self.__old_char_width = cw
                self.__old_char_height = ch
                self.__old_geom_widget = widget
        
        if old_is_hw:
            old_widget.completions_hide()
        
        self.__curtab_is_hotwire = is_hw
                
        if pn != self.__ui_merge_page_id:
            for id,actions in self.__tab_ui_merge_ids:
                self.__ui.remove_ui(id)
                self.__ui.remove_action_group(actions)
                ## Need to call ensure_update here because otherwise accelerators
                ## from the new UI will not be installed (I believe this is due
                ## to the way X keyboard grabs work)
                self.__ui.ensure_update()
            self.__ui_merge_page_id = pn
            self.__tab_ui_merge_ids = []                
            if hasattr(widget, 'get_ui_pairs'):
                for uistr,actiongroup in widget.get_ui_pairs():
                    mergeid = self.__ui.add_ui_from_string(uistr)
                    self.__ui.insert_action_group(actiongroup, -1)
                    self.__tab_ui_merge_ids.append((mergeid, actiongroup))
                self.__sync_action_acceleration()

        install_accels = is_hw
        _logger.debug("current accel install: %s new: %s", self.__nonterm_accels_installed, install_accels)
        if self.__nonterm_accels_installed != install_accels:
            if install_accels:
                _logger.debug("connecting nonterm accelerators")
            else:
                _logger.debug("disconnecting nonterm accelerators")    
            for action in self.__nonterm_actions:
                actionitem = self.__ag.get_action(action[0])
                if install_accels:
                    actionitem.connect_accelerator()
                else:
                    actionitem.disconnect_accelerator()
            self.__nonterm_accels_installed = install_accels
            
        self.__sync_title(pn)
            
    def __get_title(self, widget):
        tl = widget.get_data('hotwire-tab-label')
        if not tl:
            return None
        title = _('%s - Hotwire') % (tl.get_text(),)
        # Totally gross hack; this avoids the current situation of
        # 'sudo blah' showing up with a title of 'term -w sudo blah'.
        # Delete this if we revisit the term -w situation.
        if title.startswith('term -w'):
            title = title[7:]
        return title    
            
    def __sync_title(self, pn=None):
        if pn is not None:
            pagenum = pn
        else:
            pagenum = self.__notebook.get_current_page()
        widget = self.__notebook.get_nth_page(pagenum)
        title = self.__get_title(widget)
        if not title:
            return
        self.set_title(title)
            
    def new_tab_hotwire(self, is_initial=False, **kwargs):
        hw = Hotwire(window=self, ui=self.__ui, **kwargs)
        hw.set_data('hotwire-is-hotwire', True)

        idx = self.__notebook.append_page(hw)
        if hasattr(self.__notebook, 'set_tab_reorderable'):
            self.__notebook.set_tab_reorderable(hw, True)
        label = self.__add_widget_title(hw)

        def on_title(h, title):
            label.set_text(title)
            self.__sync_title()
        hw.connect('title', on_title)
        on_title(hw, hw.get_title())

        hw.connect('new-tab-widget', lambda h, *args: self.new_tab_widget(*args))
        hw.connect('new-window-cmd', lambda h, cmd: self.new_win_hotwire(initcmd_widget=cmd))        
        hw.show_all()
        self.__notebook.set_current_page(idx)
        self.set_focus(hw.get_entry())
        
    def new_tab_term(self, cmd):
        cwd = self.__get_curtab_cwd()
        term = Terminal.getInstance().get_terminal_widget_cmd(cwd, cmd, '')
        self.new_tab_widget(term, 'term')        

    def __sync_tabs_visible(self):
        oldvis = self.__tabs_visible
        self.__tabs_visible = len(self.__notebook.get_children()) > 1
        if self.__tabs_visible != oldvis:
            self.__notebook.set_show_tabs(self.__tabs_visible)
        self.__ag.get_action('DetachTab').set_sensitive(self.__tabs_visible)    

    def __remove_page_widget(self, w):
        savedidx = self.__preautoswitch_index
        idx = self.__notebook.page_num(w)
        _logger.debug("tab closed, preautoswitch idx: %d current: %d", savedidx, idx)
        self.__notebook.remove_page(idx)
        self.__sync_tabs_visible()
        if w in self.__closesigs:
            w.disconnect(self.__closesigs[w])
            del self.__closesigs[w]
        if self.__notebook.get_n_pages() == 0:
            self.destroy()                
        elif savedidx >= 0:
            if idx < savedidx:
                savedidx -= 1
            self.__notebook.set_current_page(savedidx)
            
    def __on_widget_closed(self, w):
        if w in self.__closesigs:
            w.disconnect(self.__closesigs[w])
            del self.__closesigs[w]
        # If a terminal exits and we're the only window, don't automatically
        # exit the app.
        if self.__notebook.get_n_pages() == 1:
            return
        self.__remove_page_widget(w)

    def __add_widget_title(self, w):
        hbox = gtk.HBox()
        label = gtk.Label('<notitle>')
        label.set_selectable(False)
        label.set_ellipsize(pango.ELLIPSIZE_END)
        hbox.pack_start(hotwidgets.Align(label, padding_right=4), expand=True)

        close = gtk.Button()
        close.set_focus_on_click(False)
        close.set_relief(gtk.RELIEF_NONE)
        close.set_name('hotwire-tab-close')
        img = gtk.Image()
        img.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        close.add(img)
        close.connect('clicked', lambda b: self.__close_tab(w))        
        (width, height) = gtk.icon_size_lookup_for_settings(label.get_settings(), gtk.ICON_SIZE_MENU)
        close.set_size_request(width + 2, height + 2)
        hbox.pack_start(close, expand=False)
        hbox.show_all()
        self.__notebook.set_tab_label(w, hbox)
        w.set_data('hotwire-tab-label', label)
        self.__notebook.set_tab_label_packing(w, True, True, gtk.PACK_START)
        self.__sync_tabs_visible()
        return label

    def __close_tab(self, w):
        self.__remove_page_widget(w)
        w.destroy()

    def new_tab_widget(self, widget, title):
        widget.set_data('hotwire-is-hotwire', False)
        savedidx = self.__notebook.get_current_page()
        idx = self.__notebook.append_page(widget)
        if hasattr(self.__notebook, 'set_tab_reorderable'):
            self.__notebook.set_tab_reorderable(widget, True)
        label = self.__add_widget_title(widget)
        label.set_text(title)
        widget.show_all()
        self.__notebook.set_current_page(idx)
        self.__closesigs[widget] = widget.connect('closed', self.__on_widget_closed)
        _logger.debug("preautoswitch idx: %d", savedidx)
        self.__preautoswitch_index = savedidx

    def new_win_hotwire(self, **kwargs):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw and 'initcwd' not in kwargs:
            kwargs['initcwd'] = widget.context.get_cwd()
        win = HotWindowFactory.getInstance().create_window(**kwargs)
        win.show()
        
    def new_win_widget(self, widget, title):
        win = HotWindowFactory.getInstance().create_window(initwidget=(widget, title))
        win.show()
        
    def get_current_widget(self):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
            return widget
        return None        

class HotWindowFactory(Singleton):
    def __init__(self):
        super(HotWindowFactory, self).__init__()
        self.__windows = set()
        self.__active_window = None
        self.__sticky_keywords = {'subtitle': ''}

    def create_initial_window(self, *args, **kwargs):
        return self.create_window(is_initial=True, *args, **kwargs)

    def create_window(self, is_initial=False, *args, **kwargs):
        _logger.debug("creating window")
        if is_initial:
            for k,v in kwargs.iteritems():
                if self.__sticky_keywords.has_key(k):
                    self.__sticky_keywords[k] = v
            kwargs['initcmd'] = 'help'
        for k,v in self.__sticky_keywords.iteritems():
            if not kwargs.has_key(k):
                kwargs[k] = v
        win = HotWindow(factory=self, is_initial=is_initial, **kwargs)
        win.connect('destroy', self.__on_win_destroy)
        win.connect('notify::is-active', self.__on_window_active)        
        self.__windows.add(win)
        if not self.__active_window:
            self.__active_window = win
        return win
    
    def run_tty_command(self, args):
        win = self.__active_window
        if not win:
            raise ValueError('No recently active window!')
        win.new_tab_term(args)
        return win

    def __on_win_destroy(self, win):
        _logger.debug("got window destroy")
        self.__windows.remove(win)
        if win == self.__active_window and len(self.__windows) > 0:
            # Pick one.
            self.__active_window = self.__windows.__iter__().next()
        if len(self.__windows) == 0:
            gtk.main_quit()

    def __on_window_active(self, win, *args):
        active = win.get_property('is-active')
        if active:
            self.__active_window = win
