# -*- tab-width: 4 -*-
import os, sys, re, logging, string

import gtk, gobject, pango

from hotwire.command import Pipeline,MinionPipeline,Command,HotwireContext
from hotwire.completion import Completion, VerbCompleter, TokenCompleter, CompletionContext, CompletionPrefixStripProxy
import hotwire.command
import hotwire.version
import hotwire_ui.widgets as hotwidgets
import hotwire_ui.pyshell
from hotwire.singletonmixin import Singleton
from hotwire.sysdep.term import Terminal
from hotwire.gutil import *
from hotwire.util import markup_for_match, quote_arg
from hotwire.fs import path_unexpanduser
from hotwire.sysdep.fs import Filesystem
try:
    from hotwire.minion import SshMinion
    minion_available = True
except:
    minion_available = False
from hotwire.state import History
from hotwire_ui.command import CommandExecutionDisplay,CommandExecutionControl
from hotwire_ui.completion import PopupDisplay
from hotwire.logutil import log_except

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

    def do_cd(self, dir):
        tree = Pipeline.parse('cd %s' % (quote_arg(dir),), self)
        self.__hotwire.execute_pipeline(tree,
                                        add_history=False,
                                        reset_input=False)

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

    def open_term(self, cwd, pipeline, arg):
        gobject.idle_add(self.__idle_open_term, cwd, pipeline, arg)

    def __idle_open_term(self, cwd, pipeline, arg):
        title = str(pipeline)
        term = Terminal.getInstance().get_terminal_widget_cmd(cwd, arg, title)
        self.__hotwire.append_tab(term, title)
        
    def get_ui(self):
        return self.__hotwire.get_global_ui()

class DownloadStatus(gtk.HBox):
    def __init__(self, fname):
        super(DownloadStatus, self).__init__()
        self.fname = fname
        bname = os.path.basename(fname)
        self.__fname = gtk.Label(bname)
        self.pack_start(self.__fname, expand=False)
        self.__progress = gtk.ProgressBar()
        self.pack_start(self.__progress, expand=True)
        self.__status = gtk.Label()
        self.pack_start(self.__status, expand=False)

    def notify_progress(self, bytes_read, bytes_total, err):
        if err:
            self.__status.set_text(err)
        elif bytes_total:
            self.__progress.set_fraction((bytes_read*1.0)/bytes_total)
            self.__status.set_text("%d/%d" % (bytes_read, bytes_total))
        else:
            self.__status.set_text("(unknown)")

class Downloads(gtk.VBox):
    def __init__(self, **args):
        super(Downloads, self).__init__(**args)
        self.__idle_removes = {}

    def __idle_remove_completed(self, child):
        self.remove(child)
        del self.__idle_removes[child.fname]
        if len(self.get_children()) == 0:
            self.hide()

    def notify_progress(self, fname, bytes_read, bytes_total, err):
        ds = None
        for child in self.get_children():
            if child.fname == fname:
                ds = child
                break
        if not ds:
            ds = DownloadStatus(fname)
            self.pack_start(ds, expand=True)
        ds.notify_progress(bytes_read, bytes_total, err)
        if bytes_read == bytes_total and not self.__idle_removes.has_key(fname):
            self.__idle_removes[fname] = (gobject.timeout_add(7000,
                                                              self.__idle_remove_completed,
                                                              ds))
        self.show_all()

class Hotwire(gtk.VBox):
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

        self.context = HotwireClientContext(self, initcwd=initcwd)
        self.context.history = History.getInstance()
        self.__tabhistory = []
        self.context.connect("cwd", self.__on_cwd)

        self.__cwd = self.context.get_cwd()

        self.__minion = None
        self.__minion_cwd = None

        self.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP,
                           [('text/uri-list', 0, 0)],
                           gtk.gdk.ACTION_COPY) 
        self.connect("drag-data-received", self.__on_drag_data_received)

        self.__paned = gtk.VBox()
        self.__topbox = gtk.VBox()
        self.__welcome = gtk.Label('Welcome to Hotwire.')
        self.__welcome_align = hotwidgets.Align(self.__welcome, yscale=1.0, xscale=1.0)
        self.__paned.pack_start(self.__welcome_align, expand=True)
        self.pack_start(self.__paned, expand=True)

        self.__outputs = CommandExecutionControl(self.context)
        self.__outputs.connect("new-window", self.__on_commands_new_window)        
        self.__topbox.pack_start(self.__outputs, expand=True)

        self.__downloads = Downloads()
        self.__topbox.pack_start(self.__downloads, expand=False)

        self.__bottom = gtk.VBox()
        self.__paned.pack_end(hotwidgets.Align(self.__bottom, xscale=1.0, yalign=1.0), expand=False)

        self.__msgline = gtk.Label('')
        self.__msgline.set_selectable(True)
        self.__msgline.set_ellipsize(True)
        self.__msgline.unset_flags(gtk.CAN_FOCUS)
        self.__bottom.pack_start(hotwidgets.Align(self.__msgline), expand=False)

        self.__active_input_completers = []
        self.__input = gtk.Entry()
        self.__shift_only = False
        self.__input.connect("notify::scroll-offset", self.__on_scroll_offset)
        self.__input.connect("notify::text", lambda *args: self.__on_input_changed())
        self.__input.connect("key-press-event", lambda i, e: self.__on_input_keypress(e))
        self.__input.connect("key-release-event", lambda i, e: self.__on_input_keyrelease(e))
        self.__input.connect("focus-out-event", self.__on_entry_focus_lost)
        self.__bottom.pack_start(self.__input, expand=False)

        self.__statusbox = gtk.VBox()
        self.__bottom.pack_start(self.__statusbox, expand=False)

        self.__statusline = gtk.HBox()
        self.__statusbox.pack_start(hotwidgets.Align(self.__statusline), expand=False)
        self.__doing_recentdir_sync = False
        self.__recentdirs = gtk.combo_box_new_text()
        self.__recentdirs.set_focus_on_click(False)
        self.__recentdirs.connect('changed', self.__on_recentdir_selected)
        self.__statusline.pack_start(hotwidgets.Align(self.__recentdirs), expand=False)

        self.__idle_parse_id = 0
        self.__parse_stale = False
        self.__pipeline_tree = None
        self.__completion_active = False
        self.__completion_active_position = False
        self.__completion_chosen = None
        self.__completion_suppress = False
        self.__completions = PopupDisplay(self.__input, window, context=self.context,
                                          tabhistory=self.__tabhistory)
        self.__completions.connect('completion-selected', self.__on_completion_selected)
        self.__completion_token = None
        self.__history_suppress = False

        self.__sync_cwd()
        self.__update_status()

        if initcmd_widget:
            self.__unset_welcome()            
            self.__outputs.add_cmd_widget(initcmd_widget)
        elif initcmd:
            gobject.idle_add(lambda: self.execute_pipeline(Pipeline.parse(initcmd, self.context), add_history=False, reset_input=False))

    def get_global_ui(self):
        return self.__ui

    def get_ui(self):
        return self.__outputs.get_ui()

    def append_tab(self, widget, title):
        self.emit("new-tab-widget", widget, title)

    def push_msg(self, msg, markup=False):
        if not markup:
            self.__msgline.set_text(msg)
        else:
            self.__msgline.set_markup(msg)

    def ssh(self, host):
        if not minion_available:
            raise NotImplementedError()
        _logger.debug("entering ssh mode host: '%s'", host)
        self.__minion = SshMinion(host)
        self.__minion.set_lcwd(self.__cwd)
        self.__minion.connect("cwd", self.__on_minion_cwd)
        self.__minion.connect("download", self.__on_download_progress)

    def __sync_cwd(self):
        max_recentdir_len = 10
        if self.__minion:
            self.__minion.set_lcwd(self.__cwd)
        model = self.__recentdirs.get_model()
        if model.iter_n_children(None) == max_recentdir_len:
            model.remove(model.iter_nth_child(None, max_recentdir_len-1))
        unexpanded = path_unexpanduser(self.__cwd)
        model.prepend((unexpanded,))
        self.__doing_recentdir_sync = True
        self.__recentdirs.set_active(0)
        self.__doing_recentdir_sync = False

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
        quoted_fpaths = map(quote_arg, urls.split('\r\n'))
        _logger.debug("path is %s, got drop paths: %s", path, quoted_fpaths)
        quoted_fpaths.append(quote_arg(path))
        self.execute_internal_str('cp ' + ' '.join(quoted_fpaths))
    
    def __on_drag_data_received(self, tv, context, x, y, selection, info, etime):
        sel_data = selection.data
        self.do_copy_url_drag_to_dir(sel_data, self.context.get_cwd())
        
    def __on_minion_cwd(self, minion, cwd):
        _logger.debug("minion cwd: '%s'", cwd)
        self.__minion_cwd = cwd
        self.__update_status()

    def __on_download_progress(self, minion, fname, bytes_read, bytes_total, err):
        _logger.debug("download progress '%s' %s %s %s", fname, bytes_read, bytes_total, err)
        self.__downloads.notify_progress(fname, bytes_read, bytes_total, err)

    def remote_active(self):
        return not not self.__minion

    def remote_exit(self):
        _logger.debug("remote exit")
        self.__minion.close()
        self.__minion = None

    def get_entry(self):
        return self.__input
    
    def grab_focus(self):
        self.__input.grab_focus()

    def __update_status(self):
        self.emit("title", self.get_title())

    def get_title(self):
        return '%s' % (os.path.basename(self.context.get_cwd()),)

    def execute_internal_str(self, pipeline_str):
        tree = Pipeline.parse(pipeline_str, self.context)
        self.execute_pipeline(tree, add_history=False, reset_input=False)        

    def execute_pipeline(self, pipeline,
                         add_history=True,
                         reset_input=True):
        _logger.debug("pipeline: %s", pipeline)

        if pipeline.is_nostatus():
            pipeline.execute_sync()

        if add_history:
            text = self.__input.get_property("text").strip()
            self.context.history.append_command(text, self.context.get_cwd())
            self.__tabhistory.insert(0, text)
            if len(self.__tabhistory) >= self.MAX_TABHISTORY:
                self.__tabhistory.pop(-1)
        if reset_input:
            self.__input.set_text("")
            self.__completion_token = None
            self.__completions.set_history_search(None)
            self.__completions.set_tab_completion(None, None)

        self.__update_status()

        if pipeline.is_nostatus():
            return

        self.__unset_welcome()

        self.__outputs.add_pipeline(pipeline)
        pipeline.execute()
        
    def __unset_welcome(self):
        if not self.__welcome:
            return
        self.__paned.remove(self.__welcome_align)
        self.__paned.pack_end(self.__topbox, expand=True)
        self.__topbox.show_all()
        self.__welcome = None
        self.__welcome_align = None        

    def __execute(self):
        self.__completions.hide()
        if self.__parse_stale:
            try:
                self.__do_parse(throw=True)
            except hotwire.command.PipelineParseException, e:
                self.push_msg("Failed to parse pipeline: %s" % (e.args[0],))
                return
        _logger.debug("executing '%s'", self.__pipeline_tree)
        if not self.__pipeline_tree or len(self.__pipeline_tree) == 0:
            _logger.debug("Nothing to execute")
            return

        # clear message if any
        self.push_msg('')

        resolutions = []
        vc = CompletionContext(VerbCompleter(self.__cwd))
        fs = Filesystem.getInstance()
        for cmd in self.__pipeline_tree:
            verb = cmd[0]
            if not verb.resolved:
                vc.set_search(verb.text, hotwire=self)
                resolution_match = None
                for match in vc.search():
                    if match.exact or fs.path_inexact_executable_match(match.mstr):
                        resolution_match = match
                    break
                if resolution_match:
                    resolutions.append((cmd, verb.text, resolution_match.get_matchdata()[0]))
                else:
                    self.push_msg('No matches for <b>%s</b>' %(gobject.markup_escape_text(verb.text),), markup=True)
                    return
        for cmd,verbtext,matchtext in resolutions:
            subtree = Pipeline.parse_tree(matchtext, context=self.context)[0]
            oldverb = cmd.pop(0)
            for i,arg in enumerate(subtree):
                cmd.insert(i, arg)

        if resolutions:
            resolutions = ['<tt>%s</tt> to <tt>%s</tt>' % (gobject.markup_escape_text(x[1]),
                                                           gobject.markup_escape_text(x[2])) for x in resolutions]
            self.push_msg('Resolved: ' + string.join(resolutions, ', '), markup=True)

        try:
            pipeline = Pipeline.parse_from_tree(self.__pipeline_tree, context=self.context)
        except hotwire.command.PipelineParseException, e:
            self.push_msg('Failed to parse pipeline: %s' % (e.args[0],))
            return

        History.getInstance().record_pipeline(self.__cwd, self.__pipeline_tree)

        text = self.__input.get_property("text")
        if self.__minion and pipeline.get_locality() != 'local':
            pipeline = MinionPipeline.parse(self.__minion, text, context=self.context)

        self.execute_pipeline(pipeline)

    @log_except(_logger)
    def __on_completion_selected(self, popup):
        _logger.debug("got completion selected")
        completion = self.__completions.select_tab_next()        
        self.__insert_completion(completion, False, True)

    def __do_completion(self, back):
        curtext = self.__input.get_property("text") 
        _logger.debug("doing completion, back=%s", back)
        if not self.__completion_active:
            valid_parse = self.__do_parse()
            if not valid_parse:
                _logger.debug("invalid parse, not completing")
                return        
        if not back:
            if not self.__completion_active:
                self.__idle_do_parse_and_complete()
            completion_do_recomplete = self.__completions.tab_is_singleton() 
            tab_prefix = self.__completions.tab_get_prefix()    
            if tab_prefix:
                completion_do_recomplete = True
                completion = tab_prefix
            else:      
                completion = self.__completions.select_tab_next()
        else:
            completion_do_recomplete = False
            completion = self.__completions.select_tab_prev()
        _logger.debug("selected completion: %s", completion)
        if not completion:
            return True
        if back and not self.__completion_active:
            _logger.debug("ignoring completion reverse when not in completion context")
            return True
        self.__insert_completion(completion, back, completion_do_recomplete)
        
    def __insert_completion(self, completion, back, completion_do_recomplete):
        curtext = self.__input.get_property("text")         
        pos = self.__input.get_position() 
        if not self.__completion_active:
            start = self.__completion_token.start
            if self.__input.get_position() < start: 
                _logger.debug("ignoring completion after edit reverse")
                return True
            target_text = curtext[self.__completion_token.start:pos]
            pre_completion = self.__completion_token.text
            if not target_text.startswith(pre_completion):
                _logger.debug("current text '%s' differs from pre-completion text '%s', requeuing parse" % (target_text, pre_completion))
                self.__do_parse_requeue()
                return True
            if target_text == pre_completion:
                # we win, keep this completion
                pass
            else:
                _logger.debug("target text differs pre-completion, bailing")
                # need to refine the results to take into account the extra text the user typed
                return True
            self.__completion_active_position = start
        else:
            start = self.__completion_active_position

        #FIXME this is broken - verb completions should return two tokens or something
        if self.__completion_token and (not isinstance(self.__completion_token, hotwire.command.ParsedVerb)) \
           and not self.__completion_token.was_unquoted: 
            completion = hotwire.command.quote_arg(completion) 

        _logger.debug("old text: %s", curtext)            
        curtext = curtext[:start] \
                  + completion \
                  + curtext[pos:] \
                  + ' '
        _logger.debug("new text: %s", curtext)
        self.__completion_chosen = completion
        self.__completion_suppress = True
        self.__input.set_text(curtext)
        self.__completion_suppress = False
        self.__parse_stale = True
        # Record that we're in TAB mode basically, so we can un-TAB
        if (not back) and (not completion_do_recomplete):
            _logger.debug("activating completion mode")
            self.__completion_active = True
            self.__unqueue_parse()
        elif completion_do_recomplete:
            _logger.debug("no further completions, requeuing parse")
            self.__queue_parse()
        insert_end = start + len(completion)
        self.__input.set_position(insert_end)
        self.__completions.reposition()

    def __handle_completion_key(self, e):
        if e.keyval == gtk.gdk.keyval_from_name('Tab'):
            self.__do_completion(False)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('ISO_Left_Tab'):
            self.__do_completion(True)
            return True
        else:
            return False

    def __on_entry_focus_lost(self, entry, e):
        self.__completions.hide()

    @log_except(_logger)
    def __on_input_keyrelease(self, e):
        shiftval = gtk.gdk.keyval_from_name('Shift_L') 
        if e.keyval == shiftval and self.__shift_only: 
            if not self.__completion_active:
                _logger.debug("got shift but no completion active, choosing first completion")
                self.__do_completion(False)
            else:    
                _logger.debug("got shift when completion active, choosing current completion")
            self.__completion_active = False
            self.__queue_parse()
        return False

    @log_except(_logger)
    def __on_input_keypress(self, e):
        curtext = self.__input.get_property("text") 

        if e.keyval == gtk.gdk.keyval_from_name('Shift_L'):
            self.__shift_only = True
        else:
            self.__shift_only = False
        if e.keyval == gtk.gdk.keyval_from_name('Return'):
            self.__execute()
            return True
        elif self.__handle_completion_key(e):
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Up') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__open_prev_output()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Down') \
             and e.state & gtk.gdk.CONTROL_MASK:
            self.__open_next_output()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Up') \
             and e.state & gtk.gdk.MOD1_MASK:
            tree = Pipeline.parse('cd ..', self.context)
            self.execute_pipeline(tree, add_history=False, reset_input=False)
        elif e.keyval == gtk.gdk.keyval_from_name('Up'):
            # If the user hits Up with an empty input, just display
            # all history
            if curtext == '' and self.__completions.get_history_search() != '':
                self.__completions.set_history_search('', now=True)
            histitem = self.__completions.select_history_next(curtext)
            if histitem is not None:
                self.__history_suppress = True
                self.__input.set_property("text", histitem)
                self.__input.set_position(-1)
                self.__history_suppress = False
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Down'):
            histitem = self.__completions.select_history_prev()
            if histitem is not None:
                self.__history_suppress = True
                self.__input.set_property("text", histitem)
                self.__input.set_position(-1)
                self.__history_suppress = False
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Escape'):
            self.__completions.hide()
            return True
        else:
            return False

    def __open_prev_output(self):
        self.__outputs.open_output(do_prev=True)

    def __open_next_output(self):
        self.__outputs.open_output()

    def __unqueue_parse(self):
        if self.__idle_parse_id > 0:
            gobject.source_remove(self.__idle_parse_id)
        self.__idle_parse_id = 0

    def __requeue_parse(self):
        self.__unqueue_parse()
        self.__idle_parse_id = gobject.timeout_add(250, self.__idle_do_parse_and_complete)        

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
        ### TODO: move more of this stuff into hotwire_ui/completion.py
        self.__completion_token = None
        self.__idle_parse_id = 0
        if not self.__do_parse():
            return
        pos = self.__input.get_position()
        prev_token = None
        completer = None
        verb = None
        addprefix = None
        # can happen when input is empty
        if not self.__pipeline_tree:
            _logger.debug("no tree, disabling completion")
            self.__completions.set_tab_completion(None, None)
            return
        for cmd in self.__pipeline_tree:
            verb = cmd[0]
            if pos >= verb.start and pos <= verb.end :
                _logger.debug("generating verb completions for '%s'", verb.text)
                completer = VerbCompleter(self.__cwd)
                self.__completion_token = verb
                addprefix='./'
                break
            prev_token = verb.text
            for i,token in enumerate(cmd[1:]):
                if not ((pos >= token.start) and (pos <= token.end)):
                    _logger.debug("skipping token (%s %s) out of %d: %s ", token.start, token.end, pos, token.text)
                    prev_token = token
                    continue
                if verb.resolved:
                    completer = verb.builtin.get_completer(i, self.context)
                else:
                    completer = None
                if not completer:
                    completer = TokenCompleter.getInstance()
                _logger.debug("generating token completions from %s for '%s'", completer, token.text)
                self.__completion_token = token
                break
        if verb and not self.__completion_token:
            _logger.debug("position at end")
            if verb and verb.resolved:
                completer = verb.builtin.get_completer(-1, self.context)
            else: 
                completer = TokenCompleter.getInstance() 
            self.__completion_token = hotwire.command.ParsedToken('', pos)
        completer = completer and CompletionPrefixStripProxy(completer, self.__cwd + os.sep, addprefix=addprefix)
        self.__completer = completer
        if self.__completer:
            self.__completer_ctx = CompletionContext(self.__completer)
            self.__completer_ctx.set_search(self.__completion_token.text, hotwire=self)
            common_prefix = self.__completer_ctx.get_common_prefix()
            _logger.debug("determined common completion prefix %s", common_prefix)
            if common_prefix and (len(self.__completion_token.text) >= len(common_prefix)):
                common_prefix = None
            self.__completions.set_tab_completion(common_prefix, self.__completer_ctx.search())
        else:
            _logger.debug("no valid completions found")
            self.__completer_ctx = None
            self.__completions.set_tab_completion(None, None)

    def __do_parse(self, throw=False):
        if not self.__parse_stale:
            return True
        text = self.__input.get_property("text")
        try:
            self.__pipeline_tree = Pipeline.parse_tree(text, self.context, accept_unclosed=(not throw))
        except hotwire.command.PipelineParseException, e:
            _logger.debug("parse failed")
            if throw:
                raise e
            return False
        _logger.debug("parse tree: %s", self.__pipeline_tree)
        self.__parse_stale = False
        return True

    def __on_input_changed(self):
        if self.__completion_suppress:
            _logger.debug("Suppressing completion change")
            return
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

    def show_all(self):
        super(Hotwire, self).show_all()
        self.__downloads.hide()
            
class HotWindow(gtk.Window):
    ascii_nums = [long(x+ord('0')) for x in xrange(10)]

    def __init__(self, factory=None, is_initial=False, subtitle='', **kwargs):
        super(HotWindow, self).__init__()

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
      <menuitem action='Close'/>
    </menu>
    <menu action='EditMenu'>
    </menu>
    <menu action='ViewMenu'>
    </menu>
    <menu action='ControlMenu'>
    </menu>
    <menu action='PrefsMenu'>
    </menu>    
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

        self.__notebook = gtk.Notebook()
        self.__notebook.connect('switch-page', lambda n, p, pn: self.__focus_page(pn))
        self.__notebook.show()
        self.__tabs_visible = self.__notebook.get_show_tabs()

        self.__geom_hints = {}
        self.__old_char_width = 0
        self.__old_char_height = 0
        self.__old_geom_widget = None
        
        self.__curtab_is_hotwire = False

        # Records the last tab index from which we created a new tab, so we 
        # can switch back when closed, unless the user manually switched tabs
        # between.
        self.__pre_autoswitch_index = -1
        
        self.set_default_size(720, 540)
        self.set_title('Hotwire' + subtitle)

        self.set_icon_name('hotwire')

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

    def get_ui(self):
        return self.__ui

    def __create_ui(self):
        self.__ag = ag = gtk.ActionGroup('WindowActions')
        actions = [
            ('FileMenu', None, 'File'),
            ('NewTermTab', gtk.STOCK_NEW, 'New T_erminal Tab', '<control><shift>T',
             'Open a new terminal tab', self.__new_term_tab_cb),
            ('Close', gtk.STOCK_CLOSE, '_Close', '<control><shift>W',
             'Close the current tab', self.__close_cb),
            ('EditMenu', None, 'Edit'),                
            ('ViewMenu', None, 'View'),       
            ('ControlMenu', None, 'Control'),
            ('PrefsMenu', None, 'Preferences'),                            
            ('ToolsMenu', None, 'Tools'),
            ('PythonWorkpad', 'gtk-execute', '_Python Workpad', '<control><alt>s', 'Launch Python evaluator', self.__python_workpad_cb),
            ('HelpCommand', 'gtk-help', '_Help', '<control><alt>h', 'Display help command', self.__help_cb),                       
            ('About', gtk.STOCK_ABOUT, '_About', None, 'About Hotwire', self.__help_about_cb),
            ]
        self.__nonterm_actions = [
            ('NewWindow', gtk.STOCK_NEW, '_New Window', '<control>n',
             'Open a new window', self.__new_window_cb),
            ('NewTab', gtk.STOCK_NEW, 'New _Tab', '<control>t',
             'Open a new tab', self.__new_tab_cb)]
        ag.add_actions(actions)
        ag.add_actions(self.__nonterm_actions)
        self.__ui = gtk.UIManager()
        self.__ui.insert_action_group(ag, 0)
        self.__ui.add_ui_from_string(self.__ui_string)
        self.__tab_ui_merge_id = None
        self.__tab_action_group = None
        self.__nonterm_accels_installed = True
        self.add_accel_group(self.__ui.get_accel_group())
        self.__hotwire_ui_mergeid = None        

    def __show_pyshell(self):
        if self.__pyshell:
            self.__pyshell.destroy()
        self.__pyshell = hotwire_ui.pyshell.CommandShell({'hotwin': self},
                                                         savepath=os.path.join(Filesystem.getInstance().get_conf_dir(), 'pypad.py'))
        self.__pyshell.set_title('Hotwire PyShell')
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
        cwd = self.__get_curtab_cwd()
        term = Terminal.getInstance().get_terminal_widget_cmd(cwd, None, '')
        self.new_tab_widget(term, 'term')

    def __close_cb(self, action):
        self.__remove_page_widget(self.__notebook.get_nth_page(self.__notebook.get_current_page()))
        if self.__notebook.get_n_pages() == 0:
            self.destroy()          

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
        comments = "An modern hybrid text/graphical shell for developers and system administrators\n\n"
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
        
        self.__curtab_is_hotwire = is_hw
                
        ## Attempt to change our UI merge; this code is a bit wonky.
        if hasattr(widget, 'get_ui'):
            (uistr, actiongroup) = widget.get_ui()
        else:
            (uistr, actiongroup) = (None, None)
        if actiongroup != self.__tab_action_group:    
            if (self.__tab_ui_merge_id is not None):
                self.__ui.remove_ui(self.__tab_ui_merge_id)
                self.__tab_ui_merge_id = None
                self.__ui.remove_action_group(self.__tab_action_group)
                self.__tab_action_group = None
                ## Need to call ensure_update here because otherwise accelerators
                ## from the new UI will not be installed (I believe this is due
                ## to the way X keyboard grabs work)
                self.__ui.ensure_update()
            if uistr is not None:
                self.__tab_ui_merge_id = self.__ui.add_ui_from_string(uistr)
                self.__tab_action_group = actiongroup
                self.__ui.insert_action_group(actiongroup, -1)         

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
            
    def new_tab_hotwire(self, is_initial=False, **kwargs):
        hw = Hotwire(window=self, ui=self.__ui, **kwargs)
        hw.set_data('hotwire-is-hotwire', True)

        idx = self.__notebook.append_page(hw)
        if hasattr(self.__notebook, 'set_tab_reorderable'):
            self.__notebook.set_tab_reorderable(hw, True)
        label = self.__add_widget_title(hw)

        hw.connect('title', lambda h, title: label.set_text(title))
        label.set_text(hw.get_title())

        hw.connect('new-tab-widget', lambda h, *args: self.new_tab_widget(*args))
        hw.connect('new-window-cmd', lambda h, cmd: self.new_win_hotwire(initcmd_widget=cmd))        
        hw.show_all()
        self.__notebook.set_current_page(idx)
        self.set_focus(hw.get_entry())

    def __sync_tabs_visible(self):
        oldvis = self.__tabs_visible
        self.__tabs_visible = len(self.__notebook.get_children()) > 1
        if self.__tabs_visible != oldvis:
            self.__notebook.set_show_tabs(self.__tabs_visible)

    def __remove_page_widget(self, w):
        savedidx = self.__preautoswitch_index
        idx = self.__notebook.page_num(w)
        _logger.debug("tab closed, preautoswitch idx: %d current: %d", savedidx, idx)
        self.__notebook.remove_page(idx)
        self.__sync_tabs_visible()
        if savedidx >= 0:
            if idx < savedidx:
                savedidx -= 1
            self.__notebook.set_current_page(savedidx)

    def __add_widget_title(self, w):
        hbox = gtk.HBox()
        label = gtk.Label('<notitle>')
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
        widget.connect('closed', self.__remove_page_widget)
        _logger.debug("preautoswitch idx: %d", savedidx)
        self.__preautoswitch_index = savedidx

    def new_win_hotwire(self, **kwargs):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
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
        self.__windows.add(win)
        return win

    def __on_win_destroy(self, win):
        _logger.debug("got window destroy")
        self.__windows.remove(win)
        if len(self.__windows) == 0:
            gtk.main_quit()
