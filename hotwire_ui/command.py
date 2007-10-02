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

class CommandExecutionDisplay(gtk.VBox):
    __gsignals__ = {
        "close" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        "visible" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        "complete" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }
    def __init__(self, context, pipeline, **args):
        super(CommandExecutionDisplay, self).__init__(**args)
        self.__pipeline = pipeline
        self.__visible = True
        self.__cancelled = False
        self.__undone = False
        self.__exception = False
        self.__mouse_hovering = False

        self.__pipeline.connect("status", self.__on_pipeline_status)
        self.__pipeline.connect("exception", self.__on_pipeline_exception)
        
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
        self.__state = 'waiting'
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

        self.__objects = MultiObjectsDisplay(context, suppress_noyield=not not status_cmds)
        self.__objects.append_ostream(pipeline.get_output_type(), None,
                                      pipeline.get_output(), False)
        self.__objects.connect("primary-complete", lambda o: self.__on_execution_complete())
        self.__objects.connect("changed", lambda o: self.__update_titlebox())
        for aux in pipeline.get_auxstreams():
            self.__objects.append_ostream(aux.schema.otype, aux.name, aux.queue, aux.schema.merge_default)
                
        self.pack_start(self.__objects, expand=(self.__pipeline.get_output_type() is not None))

        self.__exception_text = gtk.Label() 
        self.pack_start(self.__exception_text, expand=False)
        self.__exception_text.hide()

    def get_pipeline(self):
        return self.__pipeline

    def get_state(self):
        return self.__state

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

    def __toggle_visible(self):
        self.__visible = not self.__visible
        _logger.debug("toggling visiblity %s: %s", self.__visible, self.__pipeline)
        if self.__objects:
            if self.__visible:
                self.__objects.show()
            else:
                self.__objects.hide()
        self.__update_titlebox()
        self.emit("visible", self.__visible)

    def __do_cancel(self):
        if self.__cancelled:
            return
        self.__cancelled = True
        self.__objects.cancel()
        self.__pipeline.cancel()
        self.__state = 'complete'

    def __on_action(self, w):
        if self.__state == 'executing':
            self.__do_cancel()
        elif self.__state == 'complete' and (self.__undoable and not self.__undone):
            self.__undone = True
            self.__pipeline.undo()
        elif self.__state == 'complete':
            self.emit("close")
        self.__update_titlebox()

    def set_visible(self, arg=True):
        if self.__visible != arg:
            self.__toggle_visible()

    def set_hidden(self):
        if self.__visible:
            self.__toggle_visible()

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
            
        if self.__state == 'waiting':
            set_status_action('Waiting...')
        elif self.__state == 'cancelled':
            set_status_action('Cancelled')
        elif self.__state == 'executing':
            set_status_action('Executing', 'Cancel')
        elif self.__state == 'complete':
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
            
    def execute(self):
        self.__state = 'executing'
        self.__pipeline.execute(opt_formats=self.__objects.get_opt_formats())
        self.__update_titlebox()

    def __on_pipeline_status(self, pipeline, cmdidx, cmd, *args):
        _logger.debug("got pipeline status idx=%d", cmdidx)
        self.__pipeline_status_visible = True
        statusdisp = self.__cmd_statuses.get_children()[cmdidx]
        statusdisp.set_status(*args)
        self.__update_titlebox()

    def __on_pipeline_exception(self, pipeline, cmd, e):
        if self.__state == 'complete':
            return
        _logger.debug("execution exeception for %s", self.__pipeline_str)
        self.__state = 'complete'
        self.__exception = True
        self.__exception_text.show()
        self.__exception_text.set_text("Exception %s: %s" % (e.__class__, e)) 
        self.__update_titlebox()
        self.emit("complete")

    def __on_execution_complete(self):
        if self.__state == 'complete':
            return
        _logger.debug("execution complete for %s", self.__pipeline_str)
        self.__state = 'complete'
        self.__update_titlebox()
        self.emit("complete")

    def __on_button_press(self, e):
        if e.button in (1, 3):
            menu = gtk.Menu()
            showhide = gtk.MenuItem(label=(self.__visible and 'Hide' or 'Show'))
            menu.append(showhide)
            showhide.connect("activate", lambda m: self.__toggle_visible())
            remove = gtk.MenuItem(label='Remove')
            remove.set_sensitive(self.__state != 'executing')
            menu.append(remove)
            remove.connect("activate", lambda m: self.emit("close"))
            menu.show_all()
            menu.popup(None, None, None, e.button, e.time)
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
    
class CommandExecutionGroup(gtk.VBox):
    MAX_SAVED_OUTPUT = 3
    def __init__(self, ui=None):
        super(CommandExecutionGroup, self).__init__()
        self.__ui = ui
        ui_string = '''
<ui>
  <menubar name='Menubar'>
    <menu action='ViewMenu'>      
      <menuitem action='PreviousCommand'/>
      <menuitem action='NextCommand'/>
    </menu>
  </menubar>
</ui>'''    
        ui.add_ui_from_string(ui_string)     
        actions = [
            ('PreviousCommand', gtk.STOCK_GO_UP, '_Previous', '<control>Up', 'View previous command', self.__on_previous_cmd),
            ('NextCommand', gtk.STOCK_GO_DOWN, '_Next', '<control>Down', 'View next command', self.__on_next_cmd),
        ]     
        self.__ag = ag = gtk.ActionGroup('CommandActions')
        ag.add_actions(actions)
        ui.insert_action_group(ag, 0)         
         
        self.__header = gtk.HBox()
        #self.__title = gtk.Label('Previous commands')
        #self.__header.pack_start(self.__title, expand=False)
        #uparrow = ag.get_action('PreviousCommand').create_tool_item()
        #self.__header.pack_start(uparrow, expand=False)
        #downarrow = ag.get_action('NextCommand').create_tool_item()
        #self.__header.pack_start(downarrow, expand=False)        
        self.__execstatus = gtk.Label()
        self.__header.pack_start(hotwidgets.Align(self.__execstatus, padding_left=8), expand=False)
        self.pack_start(hotwidgets.Align(self.__header, xalign=0.0), expand=False)
        self.pack_start(gtk.HSeparator(), expand=False)        
        self.__cmd_vbox = gtk.VBox()
        self.pack_start(self.__cmd_vbox, expand=True)
        self.__current_cmd_box = gtk.EventBox()
        self.pack_start(self.__current_cmd_box, expand=True)
        self.__expanded = False
        self.__cached_executing_count = 0
        self.__cached_total_count = 0
        self.__redisplay()
        
    def __on_previous_cmd(self, a):
        self.open_output(True)
        
    def __on_next_cmd(self, a):
        self.open_output(False)
        
    def expand(self):
        if self.__expanded:
            return
        _logger.debug("expanding")
        self.__expanded = True
        self.__redisplay()
        
    def unexpand(self):
        if not self.__expanded:
            return
        _logger.debug("unexpanding")        
        self.__expanded = False
        self.__redisplay()
        
    def __get_complete_commands(self):
        for child in self.__iter_prevcmds():
            if child.get_state() != 'executing':
                yield child
        
    def add_cmd(self, cmd):
        _logger.debug("adding child %s", cmd)        
        oldcmd = self.__current_cmd_box.get_child()
        if oldcmd:
            self.__current_cmd_box.remove(oldcmd)
            oldcmd.set_visible(False)
            self.__cmd_vbox.pack_start(oldcmd, expand=True)
        self.__current_cmd_box.add(cmd)
        cmd.connect("complete", self.__handle_cmd_complete)
        cmd.connect("close", self.__handle_cmd_close)        
        cmd.connect("visible", self.__handle_display_visiblity)
        self.__redisplay()
        
    def __iter_prevcmds(self):
        for child in self.__cmd_vbox.get_children():
            yield child
    
    @log_except(_logger)
    def __handle_cmd_complete(self, *args):
        self.__redisplay()
      
    @log_except(_logger)        
    def __handle_cmd_close(self, p):
        self.__cmd_vbox.remove(p) 
        self.__redisplay()    
        
    def __repack_expand(self, widget, expand, parent=None):
        container = widget.get_parent()      
        if not container or (not hasattr(container, 'set_child_packing')):
            return
        print "repack %s %s %s" % (expand, container, widget)
        (_, fill, padding, pack_type) = container.query_child_packing(widget)
        container.set_child_packing(widget, expand, fill, padding, pack_type) 
        
    @log_except(_logger)
    def __handle_display_visiblity(self, display, vis):
        current = self.__current_cmd_box.get_child()
        if current == display:
            return
        self.__repack_expand(display, vis)
        
    def __recompute(self):
        total = 0
        executing = 0
        for child in self.__iter_prevcmds():
            total += 1
            if child.get_state() == 'executing':
                executing += 1
        self.__cached_total_count = total
        self.__cached_executing_count = executing        
        
    def __redisplay(self):
        complete_cmds = list(self.__get_complete_commands())
        if len(complete_cmds) > self.MAX_SAVED_OUTPUT:
            child = complete_cmds[0]
            _logger.debug("removing child %s", child)            
            child.disconnect()
            self.__cmd_vbox.remove(child)        
        self.__recompute()
        if self.__cached_executing_count > 0:
            self.__execstatus.show()
            self.__execstatus.set_text('%d executing' % (self.__cached_executing_count,))
        else:
            self.__execstatus.hide()
        current = self.__current_cmd_box.get_child() 
        if not self.__expanded:
            self.__cmd_vbox.hide()
            for child in self.__iter_prevcmds():
                child.set_hidden()
        else:
            self.__cmd_vbox.show()
        if current:
            current.set_visible(not self.__expanded)
            self.__repack_expand(self.__current_cmd_box, not self.__expanded, parent=self)            
 
    def get_last_visible(self):
        last_vis_output = None
        for output in self.__iter_prevcmds():
            if output.get_visible():
                return output
        if not last_vis_output:
            current = self.__current_cmd_box.get_child()  
            return current and current.get_visible()
 
    def open_output(self, do_prev=False):
        curvis = None
        prev = None
        prev_visible = None
        target = None
        children = list(self.__iter_prevcmds())
        if not self.__expanded and do_prev:
            self.expand()
            target = children and children[-1]
        elif not do_prev:
            children = reversed(children)
        if not target:
            for output in children:
                if not output.get_visible():
                    prev = output
                    continue
                target = prev
                break
        if target:
            target.set_visible()
            for output in children:
                if output != target and output.get_visible():
                    output.set_hidden()
        elif not do_prev:
            self.unexpand()
