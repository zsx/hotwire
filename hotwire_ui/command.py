import logging

import gtk, gobject

import hotwire_ui.widgets as hotwidgets
from hotwire_ui.odisp import MultiObjectsDisplay
from hotwire.async import QueueIterator, IterableQueue

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
        _logger.debug("toggling visiblity to %s", self.__visible)
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

    def set_visible(self):
        if not self.__visible:
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
    