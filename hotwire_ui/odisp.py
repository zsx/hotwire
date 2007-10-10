import Queue, logging

import gtk, gobject

from hotwire_ui.render import ClassRendererMapping, DefaultObjectsRenderer
import hotwire_ui.widgets as hotwidgets

_logger = logging.getLogger("hotwire.ui.ODisp")

class ObjectsDisplay(gtk.VBox):
    def __init__(self, output_spec, context, **kwargs):
        super(ObjectsDisplay, self).__init__(**kwargs)
        self.__context = context
        self.__ebox = gtk.EventBox()
        self.add(self.__ebox)
        self.__ebox.connect("key-press-event", lambda ebox, e: self.__on_keypress(e))
        self.__box = gtk.VBox()
        self.__ebox.add(self.__box)
        self.__scroll = gtk.ScrolledWindow()
        self.__scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.__search = None
        self.__old_focus = None
        self.__box.pack_start(self.__scroll, expand=True)
        self.__display = None
        self.__add_display(output_spec)
        self.__user_scrolled = False
        self.__autoscroll_id = 0

    def __add_display(self, output_spec, force=False):
        if output_spec == 'any':
            if force:
                self.__display = DefaultObjectsRenderer(self.__context)
        else:
            self.__display = ClassRendererMapping.getInstance().lookup(output_spec, self.__context)
        if self.__display:
            self.__display_widget = self.__display.get_widget()
            self.__display_widget.show_all()
            self.__scroll.add(self.__display_widget)

    def __on_keypress(self, e):
        if e.keyval in (gtk.gdk.keyval_from_name('s'), gtk.gdk.keyval_from_name('f')) and e.state & gtk.gdk.CONTROL_MASK:
            try:
                self.start_search(None)
            except NotImplementedError, e:
                pass

    def start_search(self, old_focus):
        if self.__search is None:
            self.__search = self.__display.get_search()
            if self.__search is not True:
                self.__box.pack_start(self.__search, expand=False)
                self.__search.connect("close", self.__on_search_close)
        self.__old_focus = old_focus
        if self.__search is not True:
            self.__search.show_all()
            self.__search.focus()

    def __on_search_close(self, search):
        if self.__search is not True:
            self.__search.hide()
        if self.__old_focus:
            self.__old_focus.grab_focus()
            
    def get_opt_formats(self):
        if self.__display:
            return self.__display.get_opt_formats()
        return []

    def get_objects(self):
        if self.__display:
            for obj in self.__display.get_objects():
                yield obj
                
    def append_object(self, object):
        # just in time!
        if not self.__display:
            self.__add_display(object.__class__, force=True)
        self.__display.append_obj(object)
            
    def __vadjust(self, pos, full):
        adjustment = self.__scroll.get_vadjustment()
        if not full:
            val = self.__scroll.get_vadjustment().page_increment
            if not pos:
                val = 0 - val;
            newval = adjustment.value + val
        else:
            if pos:
                newval = adjustment.upper
            else:
                newval = adjustment.lower
        newval = max(min(newval, adjustment.upper-adjustment.page_size), adjustment.lower)
        adjustment.value = newval
        self.__user_scrolled = True

    def scroll_up(self, full):
        self.__vadjust(False, full)
        
    def scroll_down(self, full):
        self.__vadjust(True, full)
        # Unpin if we're close to the bottom
        vadjust = self.__scroll.get_vadjustment()
        upper = vadjust.upper - vadjust.page_size
        if vadjust.value >= upper:
            self.__user_scrolled = False     
        
    def do_copy(self):
        if self.__display:
            return self.__display.do_copy()
        return False

    def __idle_do_autoscroll(self):
        vadjust = self.__scroll.get_vadjustment()
        vadjust.value = max(vadjust.lower, vadjust.upper - vadjust.page_size)
        self.__autoscroll_id = 0

    def do_autoscroll(self):
        if self.__display and self.__display.get_autoscroll():
            if not self.__user_scrolled:
                if self.__autoscroll_id == 0:
                    self.__autoscroll_id = gobject.timeout_add(150, self.__idle_do_autoscroll)

class MultiObjectsDisplay(gtk.Notebook):
    __gsignals__ = {
        "primary-complete" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        "changed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }
        
    def __init__(self, context, pipeline):
        super(MultiObjectsDisplay, self).__init__()
        self.__context = context
        self.__pipeline = pipeline
        self.__cancelled = False
        self.__default_odisp = None
        self.__queues = {}
        self.__ocount = 0
        self.__do_autoswitch = True
        self.__suppress_noyield = not not list(pipeline.get_status_commands())
        self.set_show_tabs(False)
        self.append_ostream(pipeline.get_output_type(), None, pipeline.get_output(), False)
        for aux in pipeline.get_auxstreams():
            self.append_ostream(aux.schema.otype, aux.name, aux.queue, aux.schema.merge_default)

    def start_search(self, old_focus):
        self.__default_odisp.start_search(old_focus)

    def do_copy(self):
        return self.__default_odisp.do_copy()

    def get_opt_formats(self):
        if self.__default_odisp:
            return self.__default_odisp.get_opt_formats()
        return []

    def get_objects(self):
        for obj in self.__default_odisp.get_objects():
            yield obj

    def append_ostream(self, otype, name, queue, merged):
        label = name or ''
        if merged:
            odisp = self.__default_odisp
        elif not (otype is None):
            odisp = ObjectsDisplay(otype, self.__context) 
            if name is None:
                self.__default_odisp = odisp
                self.__default_odisp
                self.insert_page(odisp, position=0)
                self.set_tab_label_text(odisp, name or 'Default')
                odisp.show_all()
        elif not self.__suppress_noyield:
            self.__noobjects = gtk.Label()
            self.__noobjects.set_alignment(0, 0)
            self.__noobjects.set_markup('<i>(Pipeline yields no objects)</i>')
            self.__noobjects.show()
            self.insert_page(self.__noobjects, position=0)
            odisp = None
        else:
            odisp = None
        self.__queues[queue] = (odisp, name, merged)
        queue.connect(self.__idle_handle_output)

    def cancel(self):
        self.__cancelled = True
        for queue in self.__queues.iterkeys():
            queue.disconnect()

    def get_ocount(self):
        return self.__ocount

    def __idle_handle_output(self, queue):
        if self.__cancelled:
            return False
        empty = False
        changed = False
        (odisp, name, merged) = self.__queues[queue]
        odisp_displayed = odisp in self.get_children()
        active_odisp = False
        maxitems = 100
        i = 0
        try:
            while i < maxitems:
                i += 1
                item = queue.get(False)
                changed = True
                if item is None:
                    if name is None:
                        self.emit("primary-complete")
                    empty = True
                    queue.disconnect()
                    break
                _logger.debug("appending item: %s", item)
                if odisp:
                    if not odisp_displayed:
                        self.append_page(odisp)
                        odisp.show_all()
                        self.set_tab_label_text(odisp, name or 'Default')
                        self.set_show_tabs(True)
                        odisp_displayed = True
                    odisp.append_object(item)
                    self.__ocount += 1
                    if self.__do_autoswitch:
                        self.set_current_page(self.page_num(odisp))
                        self.__do_autoswitch = False
                    active_odisp = True
                else:
                    _logger.warn("Unexpected item %s from queue %s", name, item)
        except Queue.Empty:
            pass
        if empty:
            del self.__queues[queue]
        if active_odisp:
            odisp.do_autoscroll()
        if changed:
            self.emit("changed")
        return (not empty) and (i == maxitems)

    def scroll_up(self, full=False):
        self.get_nth_page(self.get_current_page()).scroll_up(full)
        
    def scroll_down(self, full=False):
        self.get_nth_page(self.get_current_page()).scroll_down(full)

