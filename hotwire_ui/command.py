import logging

import gtk, gobject

import hotwire_ui.widgets as hotwidgets
from hotwire_ui.odisp import MultiObjectsDisplay
from hotwire.async import QueueIterator, IterableQueue
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
        "setvisible" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "complete" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }
    def __init__(self, context, pipeline, odisp, **args):
        super(CommandExecutionHeader, self).__init__(**args)
        self.__pipeline = pipeline
        self.__visible = True
        self.__cancelled = False
        self.__undone = False
        self.__exception = False
        self.__mouse_hovering = False

        self.__pipeline.connect("state-changed", self.__on_pipeline_state_change)
        self.__pipeline.connect("status", self.__on_pipeline_status)
        
        self.__titlebox_ebox = gtk.EventBox()
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
            self.__cmd_statuses = gtk.HBox()
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

    def start_search(self, old_focus):
        if self.__objects:
            self.__objects.start_search(old_focus)

    def do_copy_or_cancel(self):
        if self.__objects:
            if not self.__objects.do_copy():
                self.__do_cancel()
                self.__update_titlebox()
            else:
                return True
        return False

    def disconnect(self):
        self.__pipeline.disconnect()

    def get_output_type(self):
        return self.__pipeline.get_output_type()

    def get_output(self):
        # Can't just return objects directly as this can be
        # called from other threads
        # TODO make this actually async
        queue = IterableQueue()
        gobject.idle_add(self.__enqueue_output, queue)
        for obj in QueueIterator(queue):
            yield obj

    def __enqueue_output(self, queue):
        for obj in self.__objects.get_objects():
            queue.put(obj)
        queue.put(None)

    def __do_cancel(self):
        if self.__pipeline.get_state() != 'executing':
            return
        self.__objects.cancel()
        self.__pipeline.cancel()

    def __on_action(self, w):
        if self.get_state() == 'executing':
            self.__do_cancel()
        elif self.get_state() == 'complete' and (self.__pipeline.get_undoable()):
            self.__pipeline.undo()
        self.__update_titlebox()

    def get_objects_widget(self):
        return self.__objects

    def __update_titlebox(self):
        if self.__mouse_hovering:
            self.__title.set_markup('<tt><u>%s</u></tt>' % (gobject.markup_escape_text(self.__pipeline_str),))
        else:
            self.__title.set_markup('<tt>%s</tt>' % (gobject.markup_escape_text(self.__pipeline_str),))
            
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
            
        state = self.get_state()
        if state == 'waiting':
            set_status_action('Waiting...')
        elif state == 'cancelled':
            set_status_action('Cancelled')
        elif state == 'executing':
            set_status_action('Executing', 'Cancel')
        elif state == 'complete':
            def _color(str, color):
                return '<span foreground="%s">%s</span>' % (color,gobject.markup_escape_text(str))
            if self.__undoable and (not (self.__cancelled or self.__undone)):
                action = 'Undo'
            else:
                action = ''
            if self.__exception:
                set_status_action(_color("Exception", "red"), action, status_markup=True)
            elif self.__cancelled:
                set_status_action(_color('Cancelled', "red"), action, status_markup=True)
            elif self.__undone:
                set_status_action(_color('Undone', "red"), action, status_markup=True)
            else:
                set_status_action('Complete', action)

    def __on_pipeline_status(self, pipeline, cmdidx, cmd, *args):
        _logger.debug("got pipeline status idx=%d", cmdidx)
        self.__pipeline_status_visible = True
        statusdisp = self.__cmd_statuses.get_children()[cmdidx]
        statusdisp.set_status(*args)
        self.__update_titlebox()

    def __on_pipeline_state_change(self, pipeline):
        _logger.debug("state change for pipeline %s", self.__pipeline_str)
        state = self.__pipeline.get_state()
        self.__update_titlebox()         
        if state == 'executing':
            return
        elif state in ('cancelled', 'complete'):
            pass
        elif state == 'exception':
            self.__exception_text.show()
            excinfo = self.__pipeline.get_exception_info()
            self.__exception_text.set_text("Exception %s: %s" % (excinfo[0], excinfo[1]))
        else:
            raise Exception("Unknown state %s" % (state,)) 
        self.emit("complete")

    def __on_button_press(self, e):
        if e.button == 1:
            self.emit('setvisible')
            return True
        return False

    def __on_enter(self, w, c):
        self.__talk_to_the_hand(True)

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
        self.cmd_header = CommandExecutionHeader(context, pipeline, odisp)
        self.pack_start(self.cmd_header, expand=False)
        self.pack_start(odisp, expand=True)
    
class CommandExecutionHistory(gtk.VBox):
    __gsignals__ = {
        "show-command" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
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
        cmd.show_all()
        cmd.connect("setvisible", self.__handle_cmd_show)        
        self.__cmd_overview.pack_start(cmd, expand=False)
        
    def scroll_to_bottom(self):
        vadjust = self.__cmd_overview_scroll.get_vadjustment()
        vadjust.value = max(vadjust.lower, vadjust.upper - vadjust.page_size)        
        
    @log_except(_logger)
    def __handle_cmd_show(self, cmd):
        self.emit("show-command", cmd)        
    
class CommandExecutionControl(gtk.VBox):
    MAX_SAVED_OUTPUT = 3
    def __init__(self, context, ui):
        super(CommandExecutionControl, self).__init__()
        self.__context = context
        self.__header = gtk.HBox()
        self.__header.pack_start(gtk.Arrow(gtk.ARROW_UP, gtk.SHADOW_IN), expand=False)   
        self.__header_label = gtk.Label()
        self.__header.pack_start(hotwidgets.Align(self.__header_label), expand=False)
        self.pack_start(hotwidgets.Align(self.__header, xalign=0.0), expand=False)
        self.__cmd_notebook = gtk.Notebook()
        self.__cmd_notebook.connect('switch-page', self.__on_page_switch)
        self.__cmd_notebook.set_show_tabs(False)
        self.__cmd_notebook.set_show_border(False)
        self.pack_start(self.__cmd_notebook, expand=True)        
        self.__cmd_overview = CommandExecutionHistory(self.__context)
        self.__cmd_overview.connect('show-command', self.__on_show_command)
        self.pack_start(self.__cmd_overview, expand=True)
        self.__footer = gtk.HBox()
        self.__footer.pack_start(gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_IN), expand=False)           
        self.__footer_label = gtk.Label()
        self.__footer.pack_start(hotwidgets.Align(self.__footer_label), expand=False)        
        self.pack_start(hotwidgets.Align(self.__footer, xalign=0.0), expand=False)        
        self.__history_visible = False
        self.__cached_executing_count = 0
        self.__cached_total_count = 0
        self.__sync()
        
    def __get_complete_commands(self):
        for child in self.__iter_prevcmds():
            if child.get_state() != 'executing':
                yield child
        
    def add_pipeline(self, pipeline):
        _logger.debug("adding child %s", pipeline)
        odisp = MultiObjectsDisplay(self.__context, pipeline) 
        cmd = CommandExecutionDisplay(self.__context, pipeline, odisp)
        cmd.show_all()
        pgnum = self.__cmd_notebook.append_page(cmd)
        self.__cmd_notebook.set_current_page(pgnum)
        self.__cmd_overview.add_pipeline(pipeline, odisp)
        self.__sync()
        
    def __iter_prevcmds(self):
        for child in self.__cmd_notebook.get_children():
            yield child.cmd_header
    
    @log_except(_logger)
    def __handle_cmd_complete(self, *args):
        self.__redisplay()
      
    @log_except(_logger)        
    def __on_show_command(self, overview, cmd):
        _logger.debug("showing command %s", cmd)
        self.__toggle_history_expanded()
        target = None
        for child in self.__cmd_notebook.get_children():
            if child.cmd_header.get_pipeline() == cmd.get_pipeline():
                target = child
                break
        if target:
            pgnum = self.__cmd_notebook.page_num(target)
            self.__cmd_notebook.set_current_page(pgnum)       
 
    def get_last_visible(self):
        page = self.__cmd_notebook.get_current_page()
        if page < 0:
            return None
        return self.__cmd_notebook.get_nth_page(page)
    
    def __toggle_history_expanded(self):
        self.__history_visible = not self.__history_visible
        self.__sync()
        
    def __sync(self):
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
 
    def __on_page_switch(self, notebook, page, nth):
        n_pages = self.__cmd_notebook.get_n_pages()
        diff = (n_pages-1) - nth
        def set_label(container, label, n):
            if n == 0:
                container.hide_all()
                return
            container.show_all()
            label.set_text(' %d commands' % (n,))
        set_label(self.__header, self.__header_label, nth)
        set_label(self.__footer, self.__footer_label, diff)      
 
    def open_output(self, do_prev=False, dry_run=False):
        nth = self.__cmd_notebook.get_current_page()
        n_pages = self.__cmd_notebook.get_n_pages()
        _logger.debug("histmode: %s do_prev: %s nth: %s n_pages: %s", self.__history_visible, do_prev, nth, n_pages)   
        if nth == (n_pages-1):             
            if self.__history_visible and do_prev:
                if dry_run:
                    return True
                self.__toggle_history_expanded()
            elif (self.__history_visible and not do_prev) or (not self.__history_visible and do_prev):
                if dry_run:
                    return True
                self.__toggle_history_expanded()
                return                                
        if do_prev and nth > 0:
            target_nth = nth - 1
        elif (not do_prev) and nth < n_pages-1:
            target_nth = nth + 1        
        else:
            return False
        if dry_run:
            return True
        self.__cmd_notebook.set_current_page(target_nth)
