import os, sys, logging, StringIO, traceback

import cairo, gtk, gobject, pango

_logger = logging.getLogger("hotwire.Editor")

try:
    import gtksourceview
    gtksourceview_avail = True
    _logger.debug("gtksourceview available")
except ImportError, e:
    gtksourceview_avail = False
    _logger.debug("gtksourceview not available")

class HotEditorWindow(gtk.Window):
    def __init__(self, filename=None, content=None, title=None):
        gtk.Window.__init__(self, type=gtk.WINDOW_TOPLEVEL)
        vbox = gtk.VBox()
        self.add(vbox)
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <menuitem action='Revert'/>
      <menuitem action='Close'/>
    </menu>
    <menu action='EditMenu'>
      <menuitem action='Undo'/>
      <menuitem action='Redo'/>
    </menu>
  </menubar>
</ui>
"""
        self.__create_ui()
        vbox.pack_start(self._ui.get_widget('/Menubar'), expand=False)

        self.__filename = filename
         
        self.__save_text_id = 0

        self.gtksourceview_mode = gtksourceview_avail

        if gtksourceview_avail:
            self.input = gtksourceview.SourceBuffer()
            self.input_view = gtksourceview.SourceView(self.input)
            self.input.connect('can-undo', lambda *args: self.__sync_undoredo())
            self.input.connect('can-redo', lambda *args: self.__sync_undoredo())
        else:
            self.input = gtk.TextBuffer()
            self.input_view = gtk.TextView(self.input)
        self.input_view.set_wrap_mode(gtk.WRAP_WORD)
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)        
        scroll.add(self.input_view)
        
        vbox.pack_start(scroll, True, True)

        if filename and os.path.isfile(self.__filename):
            _logger.debug("reading %s", self.__filename)
            f = open(self.__filename, 'r')
            self.__original_text = f.read()
        else:
            self.__original_text = content
            
        if self.__original_text:
            if gtksourceview_avail:
                self.input.begin_not_undoable_action()
            self.input.set_property('text', self.__original_text)
            if gtksourceview_avail:
                self.input.end_not_undoable_action()            
        
        self.input.move_mark_by_name('insert', self.input.get_start_iter())
        self.input.move_mark_by_name('selection_bound', self.input.get_start_iter())

        self.__statusbar = gtk.Statusbar()
        self.__statusbar_ctx = self.__statusbar.get_context_id("HotEditor")
        vbox.pack_start(self.__statusbar, expand=False)
        self.__sync_undoredo()

        # do this later to avoid autosaving initially
        if filename:
            self.input.connect("changed", self.__handle_text_changed)

        self.connect("delete-event", lambda w, e: False)
        self.set_title(title or (filename and self.__filename) or 'Untitled Editor')
        self.set_size_request(640, 480)

    def __idle_save_text(self):
        self.__save_text_id = 0
        _logger.debug("autosaving to %s", self.__filename)
        f = open(self.__filename, 'w')
        text = self.input.get_property("text")
        f.write(text)
        f.close()
        autosaved_id = self.__statusbar.push(self.__statusbar_ctx, 'Autosaving...done')
        gobject.timeout_add(3000, lambda: self.__statusbar.remove(self.__statusbar_ctx, autosaved_id))
        _logger.debug("autosave complete")
        return False
    
    def __handle_text_changed(self, text):
        if self.__save_text_id == 0:
            self.__save_text_id = gobject.timeout_add(800, self.__idle_save_text)

    def __revert_cb(self, action):
        self.input.set_property('text', self.__original_text)

    def __close_cb(self, action):
        self.__handle_close()

    def __handle_close(self):
        _logger.debug("got close")
        self.__idle_save_text()
        self.destroy()

    def __undo_cb(self, action):
        self.input.undo()

    def __redo_cb(self, action):
        self.input.redo()

    def __sync_undoredo(self):
        if not gtksourceview_avail:
            return
        self.__actiongroup.get_action('Redo').set_sensitive(self.input.can_redo())
        self.__actiongroup.get_action('Undo').set_sensitive(self.input.can_undo())

    def __create_ui(self):
        self.__actiongroup = ag = gtk.ActionGroup('WindowActions')
        actions = [
            ('FileMenu', None, '_File'),
            ('Revert', None, '_Revert', None, 'Revert to saved text', self.__revert_cb),
            ('Close', gtk.STOCK_CLOSE, '_Close', '<control>W', 'Save and close', self.__close_cb),
            ('EditMenu', None, '_Edit')]

        if gtksourceview_avail:
            actions.extend([
            ('Undo', gtk.STOCK_UNDO, '_Undo', '<control>z', 'Undo previous action', self.__undo_cb),
            ('Redo', gtk.STOCK_REDO, '_Redo', '<control><shift>Z', 'Redo action', self.__redo_cb),
            ])
        ag.add_actions(actions)
        self._ui = gtk.UIManager()
        self._ui.insert_action_group(ag, 0)
        self._ui.add_ui_from_string(self.__ui_string)
        self.add_accel_group(self._ui.get_accel_group())
