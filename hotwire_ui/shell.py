# -*- tab-width: 4 -*-
import os, sys, re, logging, string

import gtk, gobject, pango

from hotwire.command import Pipeline,MinionPipeline,Command,HotwireContext
from hotwire.persist import Persister
from hotwire.completion import Completion, VerbCompleter, TokenCompleter, CompletionRecord, CompletionSortProxy, CompletionPrefixStripProxy
import hotwire.command
import hotwire.version
import hotwire_ui.widgets as hotwidgets
import hotwire_ui.pyshell
from hotwire.singletonmixin import Singleton
from hotwire.sysdep.term import Terminal
from hotwire.util import markup_for_match, quote_arg
try:
    from hotwire.minion import SshMinion
    minion_available = True
except:
    minion_available = False
from hotwire_ui.command import CommandExecutionDisplay
from hotwire_ui.completion import PopupDisplay

_logger = logging.getLogger("hotwire.ui.Shell")

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

    def get_last_output(self):
        return self.__hotwire.get_last_output()

    def get_history(self):
        return self.history.get()

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
        "new-tab-widget" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_STRING))
    }
    def __init__(self, initcwd=None, window=None):
        super(Hotwire, self).__init__()

        _logger.debug("Creating Hotwire instance, initcwd=%s", initcwd)

        self.context = HotwireClientContext(self, initcwd=initcwd)
        self.context.history = Persister.getInstance().load('history', default=[])
        self.context.connect("cwd", self.__on_cwd)

        self.__cwd = self.context.get_cwd()

        self.__minion = None
        self.__minion_cwd = None

        self.__max_visible_complete = 3

        self.__active_pipeline_count = 0

        self.__paned = gtk.VBox()
        self.__topbox = gtk.VBox()
        self.__welcome = gtk.Label('Welcome to Hotwire.')
        self.__welcome_align = hotwidgets.Align(self.__welcome, yscale=1.0, xscale=1.0)
        self.__paned.pack_start(self.__welcome_align, expand=True)
        self.pack_start(self.__paned, expand=True)

        self.__outputs = gtk.VBox()
        self.__topbox.pack_start(self.__outputs, expand=True)

        self.__downloads = Downloads()
        self.__topbox.pack_start(self.__downloads, expand=False)

        self.__bottom = gtk.VBox()
        self.__paned.pack_end(hotwidgets.Align(self.__bottom, xscale=1.0, yalign=1.0), expand=False)

        self.__msgline = gtk.Label('')
        self.__msgline.set_selectable(True)
        self.__msgline.set_ellipsize(True)
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
        self.__miniontext = gtk.Label()
        self.__statusline.pack_start(hotwidgets.Align(self.__miniontext), expand=False)
        self.__cwdtext = gtk.Label()
        self.__statusline.pack_start(hotwidgets.Align(self.__cwdtext, padding_left=8), expand=False)
        self.__status = gtk.Label()
        self.__status.set_alignment(1.0, 0.5)
        self.__statusline.pack_start(self.__status, expand=True)

        self.__statusline2 = gtk.Label()
        self.__statusbox.pack_start(self.__statusline2, expand=False)

        self.__idle_parse_id = 0
        self.__parse_stale = False
        self.__pipeline_tree = None
        self.__completion_active = False
        self.__completion_active_position = False
        self.__completion_chosen = None
        self.__completion_suppress = False
        self.__completions = PopupDisplay(self.__input, window, context=self.context)
        self.__completion_token = None
        self.__history_suppress = False
        self.__last_output = None

        self.__update_status()

        self.execute_pipeline(Pipeline.parse('help', self.context),
                              add_history=False,
                              reset_input=False)

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

    def __on_cwd(self, ctx, cwd):
        self.__cwd = cwd
        if self.__minion:
            self.__minion.set_lcwd(self.__cwd)
        self.__update_status()

    def get_last_output(self):
        last = self.__last_output
        if last:
            return (last.get_output_type(), last.get_output())
        return None
        
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

    def __handle_display_visiblity(self, display, vis):
        (expand, fill, padding, pack_type) = self.__outputs.query_child_packing(display)
        self.__outputs.set_child_packing(display, vis, fill, padding, pack_type)

    def __update_status(self):
        if self.remote_active():
            self.__miniontext.show()
        else:
            self.__miniontext.hide()
        self.__miniontext.set_text(str(self.__minion))
        self.__cwdtext.set_text(self.__minion and self.__minion_cwd or self.context.get_cwd())
        self.__status.set_text("%d active pipelines" % (self.__active_pipeline_count,))
        if self.__minion:
            self.__statusline2.set_text("(local) %s" % (self.context.get_cwd(),))
            self.__statusline2.show()
        else:
            self.__statusline2.hide()
        self.emit("title", self.get_title())

    def get_title(self):
        return '%s%s (%d)' % (self.__minion and (self.__minion + ' ') or '', os.path.basename(self.context.get_cwd()), self.__active_pipeline_count)

    def execute_pipeline(self, pipeline,
                         add_history=True,
                         reset_input=True):
        _logger.debug("pipeline: %s", pipeline)

        if pipeline.is_nostatus():
            pipeline.execute_sync()

        if add_history:
            text = self.__input.get_property("text")
            self.context.history.get(lock=True).insert(0, text.strip())
            self.context.history.save()
        if reset_input:
            self.__input.set_text("")
            self.__completion_token = None
            self.__completions.set_history_search(None)
            self.__completions.set_tab_generator(None)

        self.__update_status()

        if pipeline.is_nostatus():
            return

        if self.__welcome:
            self.__paned.remove(self.__welcome_align)
            self.__paned.pack_end(self.__topbox, expand=True)
            self.__topbox.show_all()
            self.__welcome = None
            self.__welcome_align = None

        if not (pipeline.get_output_type() is None):
            for display in self.__outputs.get_children():
                display.set_hidden()
        
        output_display = CommandExecutionDisplay(self.context, pipeline)
        output_display.connect("visible", self.__handle_display_visiblity)
        self.__active_pipeline_count += 1
        output_display.connect("complete", self.__handle_pipeline_complete)
        output_display.connect("close", self.__handle_pipeline_close)
        output_display.show_all()
        outputs = [output for output in self.__outputs.get_children() if output.get_state() == 'complete']
        if len(outputs) >= self.__max_visible_complete:
            outputs[0].disconnect()
            self.__outputs.remove(outputs[0])
        self.__outputs.pack_start(output_display, expand=(pipeline.get_output_type() is not None))
        output_display.execute()
        self.__last_output = output_display

    def __execute(self):
        self.__completions.hide()
        if self.__parse_stale:
            try:
                self.__do_parse(throw=True)
            except hotwire.command.PipelineParseException, e:
                self.push_msg("Failed to parse pipeline: %s" % (e.args[0],))
                return
        _logger.debug("executing '%s'", self.__pipeline_tree)
        if len(self.__pipeline_tree) == 0:
            _logger.debug("Nothing to execute")
            return

        # clear message if any
        self.push_msg('')

        resolutions = []
        vc = CompletionSortProxy(VerbCompleter(self.__cwd))
        for cmd in self.__pipeline_tree:
            verb = cmd[0]
            if not verb.resolved:
                matches = vc.search(verb.text, hotwire=self).__iter__()
                try: 
                    resolutions.append((cmd, verb.text, matches.next().get_matchdata()[0]))
                except StopIteration, e:
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

        CompletionRecord.getInstance().record(self.__cwd, self.__pipeline_tree)

        text = self.__input.get_property("text")
        if self.__minion and pipeline.get_locality() != 'local':
            pipeline = MinionPipeline.parse(self.__minion, text, context=self.context)

        self.execute_pipeline(pipeline)

    def __handle_pipeline_close(self, p):
        self.__outputs.remove(p)

    def __handle_pipeline_complete(self, p):
        self.__active_pipeline_count -= 1        
        self.__update_status()

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
                # need to refine the results to take into account the extra text the user typed
                return True
            self.__completion_active_position = start
        else:
            start = self.__completion_active_position

        #FIXME this is broken - verb completions should return two tokens or something
        if self.__completion_token and (not isinstance(self.__completion_token, hotwire.command.ParsedVerb)) \
           and not self.__completion_token.was_unquoted: 
            completion = hotwire.command.quote_arg(completion) 
            
        curtext = curtext[:start] \
                  + completion \
                  + curtext[pos:] \
                  + ' '
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
        elif self.__handle_output_scroll(e):
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('s') and e.state & gtk.gdk.CONTROL_MASK:
            last_vis_output = self.__get_last_vis_output()
            if not last_vis_output:
                return False
            try:
                last_vis_output.start_search(self.__input)
            except NotImplementedError, e:
                self.push_msg("Can't search this object display")
        elif e.keyval == gtk.gdk.keyval_from_name('c') and e.state & gtk.gdk.CONTROL_MASK:
            last_vis_output = self.__get_last_vis_output()
            if not last_vis_output:
                return False
            return last_vis_output.do_copy_or_cancel()
        else:
            return False

    def __open_output(self, do_prev=False):
        curvis = None
        prev = None
        prev_visible = None
        target = None
        children = self.__outputs.get_children() 
        if not do_prev:
            children = reversed(children)
        for output in children:
            if not output.get_visible():
                prev = output
                continue
            target = prev
            break
        if target:
            target.set_visible()
            for output in self.__outputs.get_children():
                if output != target and output.get_visible():
                    output.set_hidden()

    def __open_prev_output(self):
        self.__open_output(do_prev=True)

    def __open_next_output(self):
        self.__open_output()

    def __get_last_vis_output(self):
        last_vis_output = None
        for output in self.__outputs.get_children():
            if output.get_visible():
                return output
        if not last_vis_output:
            return None

    def __handle_output_scroll(self, e):
        last_vis_output = self.__get_last_vis_output()
        if not last_vis_output:
            return False
        if e.keyval == gtk.gdk.keyval_from_name('Page_Up'):
            last_vis_output.scroll_up()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Page_Down'):
            last_vis_output.scroll_down()
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('Home'):
            last_vis_output.scroll_up(True)
            return True
        elif e.keyval == gtk.gdk.keyval_from_name('End'):
            last_vis_output.scroll_down(True)
            return True
        else:
            return False

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
        self.__completion_token = None
        self.__idle_parse_id = 0
        if not self.__do_parse():
            return
        pos = self.__input.get_position()
        prev_token = None
        completer = None
        verb = None
        addprefix = None
        for cmd in self.__pipeline_tree:
            verb = cmd[0]
            if pos >= verb.start and pos <= verb.end:
                _logger.debug("generating verb completions for '%s'", verb.text)
                completer = VerbCompleter(self.__cwd)
                self.__completion_token = verb
                addprefix='./'
                break
            prev_token = verb.text
            for i,token in enumerate(cmd[1:]):
                if not ((pos >= token.start) and (pos <= token.end)):
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
        self.__completer = completer and CompletionSortProxy(completer)
        if self.__completer:
            self.__completions.set_tab_generator(self.__completer.search(self.__completion_token.text, hotwire=self))
        else:
            _logger.debug("no valid completions found")
            self.__completions.set_tab_generator(None)

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

    def controls_copypaste(self):
        return True

            
class HotWindow(gtk.Window):
    ascii_nums = [long(x+ord('0')) for x in xrange(10)]

    def __init__(self, factory=None, subtitle='', initcwd=None):
        super(HotWindow, self).__init__()

        vbox = gtk.VBox()
        self.add(vbox)
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <menuitem action='NewWindow'/>
      <menuitem action='NewTab'/>
      <separator/>
      <menuitem action='Close'/>
    </menu>
    <menu action='HelpMenu'>
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

        self.__geom_hints = {}
        self.__old_char_width = 0
        self.__old_char_height = 0
        self.__old_geom_widget = None
        
        self.set_default_size(720, 540)
        self.set_title('Hotwire' + subtitle)

        self.set_icon_name('hotwire')

        self.connect("delete-event", lambda w, e: False)

        self.connect("key-press-event", self.__on_keypress)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.__on_buttonpress)

        vbox.add(self.__notebook)
        vbox.show()

        self.new_tab_hotwire(initcwd=initcwd)

    def __create_ui(self):
        ag = gtk.ActionGroup('WindowActions')
        actions = [
            ('FileMenu', None, 'File'),
            ('NewWindow', gtk.STOCK_NEW, '_New Window', '<control><shift>N',
             'Open a new window', self.__new_window_cb),
            ('NewTab', gtk.STOCK_NEW, 'New _Tab', '<control><shift>T',
             'Open a new tab', self.__new_tab_cb),
            ('Close', gtk.STOCK_CLOSE, '_Close', '<control><shift>W',
             'Close the current tab', self.__close_cb),
            ('HelpMenu', None, 'Help'),
            ('About', gtk.STOCK_ABOUT, '_About', None, 'About Hotwire', self.__help_about_cb),
            ]
        ag.add_actions(actions)
        self.__ui = gtk.UIManager()
        self.__ui.insert_action_group(ag, 0)
        self.__ui.add_ui_from_string(self.__ui_string)
        self.add_accel_group(self.__ui.get_accel_group())

    def __show_pyshell(self):
        if self.__pyshell:
            self.__pyshell.destroy()
        self.__pyshell = hotwire_ui.pyshell.CommandShell({'hotwin': self},
                                                         histpath=os.path.join(os.path.expanduser("~"), 'hotwire-cmdshell-history'))
        self.__pyshell.set_title('Hotwire PyShell')
        self.__pyshell.show_all()

    def __on_buttonpress(self, s2, e):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        if hasattr(widget, 'on_mouse_press'):
            if widget.on_mouse_press(e):
                return True
        return False
    
    def __new_window_cb(self, action):
        self.new_win_hotwire()

    def __new_tab_cb(self, action):
        self.new_tab_hotwire()

    def __close_cb(self, action):
        self.__remove_page_widget(self.__notebook.get_nth_page(self.__notebook.get_current_page()))
        if self.__notebook.get_n_pages() == 0:
            self.destroy()

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
        comments = "An interactive hybrid text/graphical shell for developers and system administrators\n\n"
        if hotwire.version.hg_version_info:
            comments += "changeset: %s\ndate: %s\n" % (hotwire.version.hg_version_info['changeset'], hotwire.version.hg_version_info['date'],)
        dialog.set_property('comments', comments)
        dialog.run()
        dialog.destroy()

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
        elif e.keyval in (gtk.gdk.keyval_from_name('C'),
                          gtk.gdk.keyval_from_name('V')) and e.state & gtk.gdk.CONTROL_MASK:
            copy = (e.keyval == gtk.gdk.keyval_from_name('C'))
            widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
            if not widget.controls_copypaste():
                if copy:
                    widget.copy()
                else:
                    widget.paste()
        return False

    def __focus_page(self, pn):
        widget = self.__notebook.get_nth_page(pn)
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
            gobject.idle_add(self.set_focus, widget.get_entry())
            self.__old_geom_widget = widget
            self.set_geometry_hints(widget, **self.__geom_hints)          
        elif hasattr(widget, 'get_term_geometry'):
            (cw, ch, (xp, yp)) = widget.get_term_geometry()
            if (cw == self.__old_char_width and ch == self.__old_char_height and widget == self.__old_geom_widget):
                return
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

    def new_tab_hotwire(self, initcwd=None):
        hw = Hotwire(initcwd=initcwd, window=self)
        hw.set_data('hotwire-is-hotwire', True)

        idx = self.__notebook.append_page(hw)
        if hasattr(self.__notebook, 'set_tab_reorderable'):
            self.__notebook.set_tab_reorderable(hw, True)
        label = self.__add_widget_title(hw)

        hw.connect('title', lambda h, title: label.set_text(title))
        label.set_text(hw.get_title())

        hw.connect('new-tab-widget', lambda h, *args: self.new_tab_widget(*args))
        hw.show_all()
        self.__notebook.set_current_page(idx)
        self.set_focus(hw.get_entry())

    def __sync_tabs_visible(self):
        self.__notebook.set_show_tabs(len(self.__notebook.get_children()) > 1)

    def __remove_page_widget(self, w):
        idx = self.__notebook.page_num(w)
        self.__notebook.remove_page(idx)
        self.__sync_tabs_visible()

    def __add_widget_title(self, w):
        hbox = gtk.HBox()
        label = gtk.Label()
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
        idx = self.__notebook.append_page(widget)
        if hasattr(self.__notebook, 'set_tab_reorderable'):
            self.__notebook.set_tab_reorderable(widget, True)
        label = self.__add_widget_title(widget)
        label.set_text(title)
        widget.show_all()
        self.__notebook.set_current_page(idx)
        widget.connect('closed', self.__remove_page_widget)

    def new_win_hotwire(self):
        widget = self.__notebook.get_nth_page(self.__notebook.get_current_page())
        is_hw = widget.get_data('hotwire-is-hotwire')
        if is_hw:
            kwargs = {'initcwd': widget.context.get_cwd()}
        else:
            kwargs = {}
        win = HotWindowFactory.getInstance().create_window(**kwargs)
        win.show()

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
        for k,v in self.__sticky_keywords.iteritems():
            if not kwargs.has_key(k):
                kwargs[k] = v
        win = HotWindow(factory=self, **kwargs)
        win.connect('destroy', self.__on_win_destroy)
        self.__windows.add(win)
        return win

    def __on_win_destroy(self, win):
        _logger.debug("got window destroy")
        self.__windows.remove(win)
        if len(self.__windows) == 0:
            gtk.main_quit()

    
