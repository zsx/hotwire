import os, sys, logging, time

import gtk, gobject

import hotwire_ui.widgets as hotwidgets
from hotwire_ui.odisp import MultiObjectsDisplay
from hotwire.command import CommandQueue
from hotwire.async import QueueIterator
from hotwire.logutil import log_except

_logger = logging.getLogger("hotwire.ui.Command")

class CommandStatusDisplay(gtk.HBox):
    def __init__(self, cmdname):
        super(CommandStatusDisplay, self).__init__(spacing=4)
        self.__cmdname = cmdname
        self.__text = gtk.Label()
        self.pack_start(self.__text, expand=False)
        self.__progress = gtk.ProgressBar()
        self.__progress_visible = False

    def set_status(self, text, progress):
        if self.__cmdname:
            text = self.__cmdname + ' ' + text
        self.__text.set_text(text)
        if progress >= 0:
            if not self.__progress_visible:
                self.__progress_visible = True
                self.pack_start(self.__progress, expand=False)
                self.__progress.show()
            self.__progress.set_fraction(progress/100.0)

class CommandExecutionHeader(gtk.VBox):
    __gsignals__ = {
        "action" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),                    
        "setvisible" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "complete" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }
    def __init__(self, context, pipeline, odisp, highlight=True, **args):
        super(CommandExecutionHeader, self).__init__(**args)
        self.__pipeline = pipeline
        self.__visible = True
        self.__cancelled = False
        self.__undone = False
        self.__exception = False
        self.__mouse_hovering = False
        
        self.__tooltips = gtk.Tooltips()

        self.__pipeline.connect("state-changed", self.__on_pipeline_state_change)
        self.__pipeline.connect("metadata", self.__on_pipeline_metadata)
        
        self.__titlebox_ebox = gtk.EventBox()
        if highlight:
            self.__titlebox_ebox.add_events(gtk.gdk.BUTTON_PRESS_MASK
                                            & gtk.gdk.ENTER_NOTIFY_MASK
                                            & gtk.gdk.LEAVE_NOTIFY_MASK)
            self.__titlebox_ebox.connect("enter_notify_event", self.__on_enter) 
            self.__titlebox_ebox.connect("leave_notify_event", self.__on_leave) 
            self.__titlebox_ebox.connect("button-press-event", lambda eb, e: self.__on_button_press(e))

        self.__titlebox = gtk.HBox()
        self.__titlebox_ebox.add(self.__titlebox)
        self.pack_start(hotwidgets.Align(self.__titlebox_ebox), expand=False)
        self.__pipeline_str = self.__pipeline.__str__()
        self.__title = gtk.Label()
        self.__title.set_alignment(0, 0.5)
        #self.__title.set_selectable(True)        
        self.__title.set_ellipsize(True)
        self.__titlebox.pack_start(hotwidgets.Align(self.__title, padding_left=4), expand=True)
        self.__statusbox = gtk.HBox()
        self.pack_start(self.__statusbox, expand=False)
        self.__status_left = gtk.Label()
        self.__status_right = gtk.Label()
        self.__statusbox.pack_start(hotwidgets.Align(self.__status_left, padding_left=4), expand=False)
        self.__action = hotwidgets.Link()
        self.__action.connect("clicked", self.__on_action)
        self.__statusbox.pack_start(hotwidgets.Align(self.__action), expand=False)   
        self.__statusbox.pack_start(hotwidgets.Align(self.__status_right), expand=False)        
        
        self.__undoable = self.__pipeline.get_undoable() and (not self.__pipeline.get_idempotent())

        status_cmds = list(pipeline.get_status_commands())
        self.__pipeline_status_visible = False
        if status_cmds:
            self.__cmd_statuses = gtk.HBox(spacing=8)
            show_cmd_name = len(status_cmds) > 1
            for cmdname in status_cmds:
                self.__cmd_statuses.pack_start(CommandStatusDisplay(show_cmd_name and cmdname or None), expand=True)
            self.__statusbox.pack_start(hotwidgets.Align(self.__cmd_statuses), expand=False)
        else:
            self.__cmd_statuses = None
            self.__cmd_status_show_cmd = False

        self.__objects = odisp
        self.__objects.connect("changed", lambda o: self.__update_titlebox())

        self.__exception_text = gtk.Label() 
        self.pack_start(self.__exception_text, expand=False)
        self.__exception_text.hide()

    def get_pipeline(self):
        return self.__pipeline

    def get_state(self):
        return self.__pipeline.get_state()

    def get_visible(self):
        return self.__visible

    def scroll_up(self, full=False):
        if self.__objects:
            self.__objects.scroll_up(full)
        
    def scroll_down(self, full=False):
        if self.__objects:
            self.__objects.scroll_down(full)

    def disconnect(self):
        self.__pipeline.disconnect()

    def get_output_type(self):
        return self.__pipeline.get_output_type()

    def get_output(self):
        # Can't just return objects directly as this can be
        # called from other threads
        # TODO make this actually async
        queue = CommandQueue()
        gobject.idle_add(self.__enqueue_output, queue)
        for obj in QueueIterator(queue):
            yield obj

    def __enqueue_output(self, queue):
        for obj in self.__objects.get_objects():
            queue.put(obj)
        queue.put(None)

    @log_except(_logger)
    def __on_action(self, *args):
        _logger.debug("emitting action")
        self.emit('action')

    def get_objects_widget(self):
        return self.__objects

    def __update_titlebox(self):
        if self.__mouse_hovering:
            self.__title.set_markup('<tt><u>%s</u></tt>' % (gobject.markup_escape_text(self.__pipeline_str),))
        else:
            self.__title.set_markup('<tt>%s</tt>' % (gobject.markup_escape_text(self.__pipeline_str),))
            
        if self.__objects:
            self.__tooltips.set_tip(self.__titlebox_ebox, 'Output: ' + str(self.__objects.get_default_output_type()))
            
        ocount = self.__objects and self.__objects.get_ocount() or 0
            
        def set_status_action(status_text_left, action_text='', status_markup=False):
            if action_text:
                status_text_left += " ("
            if status_markup:
                self.__status_left.set_markup(status_text_left)
            else:                
                self.__status_left.set_text(status_text_left)
            if action_text:
                self.__action.set_text(action_text)
                self.__action.show()
            else:
                self.__action.set_text('')
                self.__action.hide()
            status_right_start = action_text and ')' or ''
            status_right_end = self.__pipeline_status_visible and '; ' or ''
            self.__status_right.set_text(status_right_start + (", %d objects" % (ocount,)) + status_right_end)
            
        def _color(str, color):
            return '<span foreground="%s">%s</span>' % (color,gobject.markup_escape_text(str))            
        state = self.get_state()
        if state == 'waiting':
            set_status_action('Waiting...')
        elif state == 'cancelled':
            set_status_action(_color('Cancelled', "red"), '', status_markup=True)
        elif state == 'undone':
            set_status_action(_color('Undone', "red"), '', status_markup=True)
        elif state == 'exception':
            set_status_action(_color('Exception', "red"), '', status_markup=True) 
        elif state == 'executing':
            set_status_action('Executing', 'Cancel')
        elif state == 'complete':
            set_status_action('Complete', self.__pipeline.get_undoable() and 'Undo' or '')

    def __on_pipeline_metadata(self, pipeline, cmdidx, cmd, key, flags, meta):
        _logger.debug("got pipeline metadata idx=%d key=%s flags=%s", cmdidx, key, flags)
        if key != 'hotwire.status':
            return
        self.__pipeline_status_visible = True
        statusdisp = self.__cmd_statuses.get_children()[cmdidx]
        statusdisp.set_status(*meta)
        self.__update_titlebox()

    def __on_pipeline_state_change(self, pipeline):
        state = self.__pipeline.get_state()        
        _logger.debug("state change to %s for pipeline %s", state, self.__pipeline_str)
        self.__update_titlebox()         
        if state == 'executing':
            return
        elif state in ('cancelled', 'complete', 'undone'):
            pass
        elif state == 'exception':
            self.__exception_text.show()
            excinfo = self.__pipeline.get_exception_info()
            self.__exception_text.set_text("Exception %s: %s" % (excinfo[0], excinfo[1]))
        else:
            raise Exception("Unknown state %s" % (state,)) 
        self.emit("complete")

    @log_except(_logger)
    def __on_button_press(self, e):
        if e.button == 1:
            self.emit('setvisible')
            return True
        return False

    @log_except(_logger)
    def __on_enter(self, w, c):
        self.__talk_to_the_hand(True)

    @log_except(_logger)
    def __on_leave(self, w, c):
        self.__talk_to_the_hand(False)

    def __talk_to_the_hand(self, hand):
        display = self.get_display()
        cursor = None
        if hand:
            cursor = gtk.gdk.Cursor(display, gtk.gdk.HAND2)
        self.window.set_cursor(cursor)
        self.__mouse_hovering = hand
        self.__update_titlebox()
    
class CommandExecutionDisplay(gtk.VBox):
    def __init__(self, context, pipeline, odisp):
        super(CommandExecutionDisplay, self).__init__()
        self.odisp = odisp
        self.cmd_header = CommandExecutionHeader(context, pipeline, odisp, highlight=False)
        self.pack_start(self.cmd_header, expand=False)
        self.pack_start(odisp, expand=True)
        
    def cancel(self):
        self.odisp.cancel()
        self.cmd_header.get_pipeline().cancel()
        
    def undo(self):
        self.cmd_header.get_pipeline().undo()        
    
class CommandExecutionHistory(gtk.VBox):
    __gsignals__ = {
        "show-command" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        "command-action" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),        
    }    
    def __init__(self, context):
        super(CommandExecutionHistory, self).__init__()
        self.__context = context
        self.__cmd_overview = gtk.VBox()
        self.__cmd_overview_scroll = scroll = gtk.ScrolledWindow()
        scroll.set_property('hscrollbar-policy', gtk.POLICY_NEVER)
        scroll.add_with_viewport(self.__cmd_overview)
        self.pack_start(scroll, expand=True)        

    def add_pipeline(self, pipeline, odisp):
        cmd = CommandExecutionHeader(self.__context, pipeline, odisp)
        cmd.connect('action', self.__handle_cmd_action)        
        cmd.show_all()
        cmd.connect("setvisible", self.__handle_cmd_show)        
        self.__cmd_overview.pack_start(cmd, expand=False)
        
    @log_except(_logger)
    def __handle_cmd_action(self, cmd):
        self.emit('command-action', cmd)        
        
    def get_overview_list(self):
        return self.__cmd_overview.get_children()
    
    def remove_overview(self, oview):
        self.__cmd_overview.remove(oview)
        
    def scroll_to_bottom(self):
        vadjust = self.__cmd_overview_scroll.get_vadjustment()
        vadjust.value = max(vadjust.lower, vadjust.upper - vadjust.page_size)        
        
    @log_except(_logger)
    def __handle_cmd_show(self, cmd):
        self.emit("show-command", cmd)        
    
class CommandExecutionControl(gtk.VBox):
    # This may be a sucky policy, but it's less sucky than what came before.
    COMPLETE_CMD_EXPIRATION_SECS = 5 * 60
    __gsignals__ = {
        "new-window" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }        
    def __init__(self, context):
        super(CommandExecutionControl, self).__init__()
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='EditMenu'>
      <menuitem action='Copy'/>
      <separator/>
      <menuitem action='Search'/>
      <menuitem action='Input'/> 
    </menu>
    <menu action='ViewMenu'>
      <menuitem action='Overview'/>
      <separator/>
      <menuitem action='ToWindow'/>      
      <separator/>      
      <menuitem action='PreviousCommand'/>
      <menuitem action='NextCommand'/>
    </menu>
    <menu action='ControlMenu'>
      <menuitem action='Cancel'/>
      <menuitem action='Undo'/>
    </menu>    
  </menubar>
  <accelerator action='ScrollHome'/>
  <accelerator action='ScrollEnd'/>
  <accelerator action='ScrollPgUp'/>
  <accelerator action='ScrollPgDown'/>  
</ui>"""         
        self.__actions = [
            ('Copy', None, '_Copy', '<control>c', 'Copy output', self.__copy_cb),                          
            ('Cancel', None, '_Cancel', '<control><shift>c', 'Cancel current command', self.__cancel_cb),
            ('Undo', None, '_Undo', None, 'Undo current command', self.__undo_cb),            
            ('Search', None, '_Search', '<control>s', 'Search output', self.__search_cb),
            ('Input', None, '_Input', '<control>i', 'Send input', self.__input_cb),                         
            ('ScrollHome', None, 'Output _Top', '<control>Home', 'Scroll to output top', self.__view_home_cb),
            ('ScrollEnd', None, 'Output _Bottom', '<control>End', 'Scroll to output bottom', self.__view_end_cb), 
            ('ScrollPgUp', None, 'Output Page _Up', 'Page_Up', 'Scroll output up', self.__view_up_cb),
            ('ScrollPgDown', None, 'Output Page _Down', 'Page_Down', 'Scroll output down', self.__view_down_cb),
            ('ToWindow', None, '_To Window', '<control><shift>N', 'Create window from output', self.__to_window_cb),                         
            ('PreviousCommand', gtk.STOCK_GO_UP, '_Previous', '<control>Up', 'View previous command', self.__view_previous_cb),
            ('NextCommand', gtk.STOCK_GO_DOWN, '_Next', '<control>Down', 'View next command', self.__view_next_cb),
        ]
        self.__toggle_actions = [
            ('Overview', None, '_Overview', '<control><shift>o', 'Toggle overview', self.__overview_cb),                                   
        ]
        self.__action_group = gtk.ActionGroup('HotwireActions')
        self.__action_group.add_actions(self.__actions) 
        self.__action_group.add_toggle_actions(self.__toggle_actions)
        self.__action_group.get_action('Overview').set_active(False)       
        self.__context = context
        self.__header = gtk.HBox()    
        def create_arrow_button(action_name):
            action = self.__action_group.get_action(action_name)
            icon = action.create_icon(gtk.ICON_SIZE_MENU)
            button = gtk.Button(label='x')
            button.connect('clicked', lambda *args: action.activate())
            action.connect("notify::sensitive", lambda *args: button.set_sensitive(action.get_sensitive()))
            button.set_property('image', icon)
            button.set_focus_on_click(False)            
            return button
        self.__header_label = create_arrow_button('PreviousCommand')
        self.__header.pack_start(self.__header_label, expand=False)
        self.pack_start(self.__header, expand=False)
        self.__cmd_notebook = gtk.Notebook()
        self.__cmd_notebook.connect('switch-page', self.__on_page_switch)
        self.__cmd_notebook.set_show_tabs(False)
        self.__cmd_notebook.set_show_border(False)
        self.pack_start(self.__cmd_notebook, expand=True)        
        self.__cmd_overview = CommandExecutionHistory(self.__context)
        self.__cmd_overview.show_all()
        self.__cmd_overview.set_no_show_all(True)
        self.__cmd_overview.connect('show-command', self.__on_show_command)
        self.__cmd_overview.connect('command-action', self.__handle_cmd_overview_action) 
        self.pack_start(self.__cmd_overview, expand=True)
        self.__footer = gtk.HBox()    
        self.__footer_label = create_arrow_button('NextCommand')         
        self.__footer.pack_start(self.__footer_label, expand=False) 
        self.pack_start(self.__footer, expand=False)        
        self.__history_visible = False
        self.__cached_executing_count = 0
        self.__cached_total_count = 0
        self.__sync_visible()
        self.__sync_cmd_sensitivity()
        
    def get_ui(self):
        return (self.__ui_string, self.__action_group)
    
    def __get_complete_commands(self):
        for child in self.__iter_cmds():
            if child.get_state() != 'executing':
                yield child
            
    def __iter_cmds(self):
        for child in self.__cmd_notebook.get_children():
            yield child.cmd_header            
     
    def add_cmd_widget(self, cmd):
        pipeline = cmd.cmd_header.get_pipeline()
        pipeline.connect('state-changed', self.__on_pipeline_state_change)        
        self.__cmd_overview.add_pipeline(pipeline, cmd.odisp)
        pgnum = self.__cmd_notebook.append_page(cmd)
        self.__cmd_notebook.set_current_page(pgnum)
        self.__sync_visible()
        self.__sync_display()
        gobject.idle_add(lambda: self.__sync_display())
        
    def add_pipeline(self, pipeline):
        _logger.debug("adding child %s", pipeline)
        pipeline.connect('state-changed', self.__on_pipeline_state_change)
        odisp = MultiObjectsDisplay(self.__context, pipeline) 
        cmd = CommandExecutionDisplay(self.__context, pipeline, odisp)
        cmd.cmd_header.connect('action', self.__handle_cmd_action)
        cmd.show_all()
        pgnum = self.__cmd_notebook.append_page(cmd)
        self.__cmd_notebook.set_current_page(pgnum)
        self.__cmd_overview.add_pipeline(pipeline, odisp)     
        
        # Garbage-collect old commands at this point        
        self.__command_gc()
                
        self.__sync_visible()                
        self.__sync_display(pgnum)
        
    def __command_gc(self):
        curtime = time.time()
        for cmd in self.__iter_cmds():
            pipeline = cmd.get_pipeline()
            compl_time = pipeline.get_completion_time() 
            if not compl_time:
                continue
            if curtime - compl_time > self.COMPLETE_CMD_EXPIRATION_SECS:
                self.remove_pipeline(pipeline)                        
        
    def remove_pipeline(self, pipeline, disconnect=True):
        if disconnect:
            pipeline.disconnect()
        cmdview = None
        for child in self.__cmd_notebook.get_children():
            if not child.cmd_header.get_pipeline() == pipeline:
                continue
            cmdview = child
            self.__cmd_notebook.remove(child)
        for child in self.__cmd_overview.get_overview_list():
            if not child.get_pipeline() == pipeline:
                continue
            self.__cmd_overview.remove_overview(child)
        return cmdview
    
    @log_except(_logger)
    def __handle_cmd_complete(self, *args):
        self.__sync_cmd_sensitivity()
        
    @log_except(_logger)
    def __handle_cmd_overview_action(self, oview, cmd):
        self.__handle_cmd_action(cmd)
        
    @log_except(_logger)
    def __handle_cmd_action(self, cmd):
        pipeline = cmd.get_pipeline()
        _logger.debug("handling action for %s", pipeline)        
        if pipeline.validate_state_transition('cancelled'):
            _logger.debug("doing cancel")
            pipeline.cancel()
        elif pipeline.validate_state_transition('undone'):
            _logger.debug("doing undo")            
            pipeline.undo()                    
        else:
            raise ValueError("Couldn't do action %s from state %s" % (action,cmd.cmd_header.get_pipeline().get_state()))        
      
    @log_except(_logger)        
    def __on_show_command(self, overview, cmd):
        _logger.debug("showing command %s", cmd)
        target = None
        for child in self.__cmd_notebook.get_children():
            if child.cmd_header.get_pipeline() == cmd.get_pipeline():
                target = child
                break
        if target:
            pgnum = self.__cmd_notebook.page_num(target)
            self.__cmd_notebook.set_current_page(pgnum)
            self.__action_group.get_action("Overview").activate()
            from hotwire_ui.shell import locate_current_shell
            hw = locate_current_shell(self)
            hw.grab_focus()                        
 
    def get_current(self):
        cmd = self.get_current_cmd(full=True)
        return cmd and cmd.odisp
 
    def get_current_cmd(self, full=False, curpage=None):
        if curpage is not None:
            page = curpage
        else:
            page = self.__cmd_notebook.get_current_page()
        if page < 0:
            return None
        cmd = self.__cmd_notebook.get_nth_page(page)
        if full:
            return cmd
        return cmd.cmd_header

    def __copy_cb(self, a):
        _logger.debug("doing copy cmd")
        cmd = self.get_current_cmd(full=True)
        cmd.odisp.do_copy()
    
    def __cancel_cb(self, a):
        _logger.debug("doing cancel cmd")
        cmd = self.get_current_cmd(full=True)
        cmd.cancel()
        
    def __undo_cb(self, a):
        _logger.debug("doing undo cmd")
        cmd = self.get_current_cmd(full=True)
        cmd.undo()        
        
    def __search_cb(self, a):
        cmd = self.get_current_cmd(full=True)
        top = self.get_toplevel()
        lastfocused = top.get_focus()
        cmd.odisp.start_search(lastfocused)
        
    def __input_cb(self, a):
        cmd = self.get_current_cmd(full=True)
        top = self.get_toplevel()
        lastfocused = top.get_focus()
        cmd.odisp.start_input(lastfocused)        
    
    def __view_previous_cb(self, a):
        self.open_output(True)
        
    def __view_next_cb(self, a):
        self.open_output(False)
        
    def __view_home_cb(self, a):
        self.__do_scroll(True, True)
        
    def __view_end_cb(self, a):
        self.__do_scroll(False, True)    
        
    def __view_up_cb(self, a):
        self.__do_scroll(True, False)
        
    def __view_down_cb(self, a):
        self.__do_scroll(False, False)
    
    def __to_window_cb(self, a):
        cmd = self.get_current_cmd(full=True)
        pipeline = cmd.cmd_header.get_pipeline()
        #pipeline.disconnect('state-changed', self.__on_pipeline_state_change)                 
        cmdview = self.remove_pipeline(pipeline, disconnect=False)
        self.emit('new-window', cmdview)
        self.__sync_display()

    def __overview_cb(self, a): 
        self.__toggle_history_expanded()
    
    def __do_scroll(self, prev, full):
        cmd = self.get_current_cmd()
        if prev:
            cmd.scroll_up(full)
        else:
            cmd.scroll_down(full)
        
    def __toggle_history_expanded(self):
        self.__history_visible = not self.__history_visible
        _logger.debug("history visible: %s", self.__history_visible)
        self.__sync_visible()
        self.__sync_cmd_sensitivity()
        self.__sync_display()
        if self.__history_visible:
            self.__cmd_overview.scroll_to_bottom()            
        
    def __sync_visible(self):
        if self.__history_visible:
            self.__cmd_overview.show()
            self.__cmd_notebook.hide()
            self.__header.hide()
            self.__footer.hide()
        else:
            self.__cmd_overview.hide()
            self.__cmd_notebook.show() 
            self.__header.show()
            self.__footer.show()
            
    @log_except(_logger)
    def __on_pipeline_state_change(self, pipeline):
        _logger.debug("handling state change to %s", pipeline.get_state())
        self.__sync_cmd_sensitivity()
            
    def __sync_cmd_sensitivity(self, curpage=None):
        actions = map(self.__action_group.get_action, ['Copy', 'Cancel', 'PreviousCommand', 'NextCommand', 'Undo', 'Input'])
        if self.__history_visible:
            for action in actions:
                action.set_sensitive(False)
            cmd = None
            return
        else:            
            cmd = self.get_current_cmd(full=True, curpage=curpage)
            if not cmd:
                for action in actions:
                    action.set_sensitive(False)
                    return
            _logger.debug("sync sensitivity page %s pipeline: %s", curpage, cmd.cmd_header.get_pipeline().get_state())                
            cancellable = not not (cmd and cmd.cmd_header.get_pipeline().validate_state_transition('cancelled'))
            undoable = not not (cmd and cmd.cmd_header.get_pipeline().validate_state_transition('undone'))
            _logger.debug("cancellable: %s undoable: %s", cancellable, undoable)
            actions[1].set_sensitive(cancellable)
            actions[4].set_sensitive(undoable)
            actions[5].set_sensitive(cmd and cmd.odisp.supports_input() or False)
        actions[2].set_sensitive(self.__get_prevcmd_count(curpage) > 0)
        actions[3].set_sensitive(self.__get_nextcmd_count(curpage) > 0)
        
    def __sync_display(self, nth=None):
        def set_label(container, label, n):
            if n <= 0 or self.__history_visible:
                container.hide_all()
                return
            container.show_all()
            label.set_label(' %d commands' % (n,))
        set_label(self.__header, self.__header_label, self.__get_prevcmd_count(nth))
        set_label(self.__footer, self.__footer_label, self.__get_nextcmd_count(nth))
        self.__sync_cmd_sensitivity(curpage=nth)        
        
    def __get_prevcmd_count(self, cur=None):
        if cur is not None:
            return cur
        return self.__cmd_notebook.get_current_page()
    
    def __get_nextcmd_count(self, cur=None):
        if cur is not None:
            nth = cur
        else:       
            nth = self.__cmd_notebook.get_current_page()        
        n_pages = self.__cmd_notebook.get_n_pages()
        return (n_pages-1) - nth        
 
    def __on_page_switch(self, notebook, page, nth):
        self.__sync_display(nth=nth)
 
    def open_output(self, do_prev=False, dry_run=False):
        nth = self.__cmd_notebook.get_current_page()
        n_pages = self.__cmd_notebook.get_n_pages()
        _logger.debug("histmode: %s do_prev: %s nth: %s n_pages: %s", self.__history_visible, do_prev, nth, n_pages)
        if do_prev and nth > 0:
            target_nth = nth - 1
        elif (not do_prev) and nth < n_pages-1:
            target_nth = nth + 1        
        else:
            return False
        if dry_run:
            return True
        self.__cmd_notebook.set_current_page(target_nth)
        from hotwire_ui.shell import locate_current_shell
        hw = locate_current_shell(self)
        hw.grab_focus()         
        
