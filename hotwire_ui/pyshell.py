import os, sys, logging, StringIO, traceback

import cairo, gtk, gobject, pango

from hotwire_ui.editor import HotEditorWindow

_logger = logging.getLogger("hotwire.PyShell")

class OutputWindow(gtk.Window):
    def __init__(self, content):
        super(OutputWindow, self).__init__(gtk.WINDOW_TOPLEVEL)
        vbox = gtk.VBox()
        self.add(vbox)
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='FileMenu'>
      <menuitem action='Close'/>
    </menu>
  </menubar>
</ui>
"""
        self.__create_ui()
        vbox.pack_start(self._ui.get_widget('/Menubar'), expand=False)        
        self.output = gtk.TextBuffer()
        self.output_view = gtk.TextView(self.output)
        self.output_view.set_wrap_mode(gtk.WRAP_WORD)
        self.output_view.set_property("editable", False)
        self.output.set_property('text', content)
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
        scroll.add(self.output_view)
        vbox.pack_start(scroll, True, True)
        self.set_size_request(640, 480)        
        
    def __create_ui(self):
        self.__actiongroup = ag = gtk.ActionGroup('OutputWindowActions')
        actions = [
            ('FileMenu', None, 'File'),
            ('Close', gtk.STOCK_CLOSE, '_Close', 'Return', 'Close window', self.__close_cb),
            ]
        ag.add_actions(actions)
        self._ui = gtk.UIManager()
        self._ui.insert_action_group(ag, 0)
        self._ui.add_ui_from_string(self.__ui_string)
        self.add_accel_group(self._ui.get_accel_group()) 
        
    def __close_cb(self, action):
        self.destroy()               
        
class CommandShell(HotEditorWindow):
    DEFAULT_CONTENT = '''## Hotwire Python Pad
## Global values:
##   outln(value): (Function) Print a value and a newline to output stream
##   hotwin: (Value) The global Hotwire window
import os,sys,re
import gtk, gobject

outln('''
    def __init__(self, locals={}, savepath=None):
        super(CommandShell, self).__init__(content=self.DEFAULT_CONTENT, filename=savepath)
        self._locals = locals
        self.__ui_string = """
<ui>
  <menubar name='Menubar'>
    <menu action='ToolsMenu'>
      <menuitem action='Eval'/>
    </menu>
  </menubar>
</ui>        
"""    
        actions = [
            ('ToolsMenu', None, 'Tools'),
            ('Eval', None, '_Eval', '<control>Return', 'Evaluate current input', self.__eval_cb),
            ]
        self.__actiongroup = ag = gtk.ActionGroup('ShellActions')        
        ag.add_actions(actions)
        self._ui.insert_action_group(ag, 0)
        self._ui.add_ui_from_string(self.__ui_string)

        if self.gtksourceview_mode:
            import gtksourceview            
            pylang = gtksourceview.SourceLanguagesManager().get_language_from_mime_type("text/x-python")
            self.input.set_language(pylang)
            self.input.set_highlight(True)
            
        self.input.move_mark_by_name("insert", self.input.get_end_iter())
        self.input.move_mark_by_name("selection_bound", self.input.get_end_iter())        
            
        self.set_title('Hotwire Command Shell')
        self.input_view.modify_font(pango.FontDescription("monospace"))        

    def __eval_cb(self, a):
        try:
            output_stream = StringIO.StringIO()
            text = self.input.get_property("text")
            code_obj = compile(text, '<input>', 'exec')
            locals = {}
            for k, v in self._locals.items():
                locals[k] = v
            locals['output'] = output_stream
            locals['outln'] = lambda v: self.__outln(output_stream, v)
            exec code_obj in locals
            _logger.debug("execution complete with %d output characters" % (len(output_stream.getvalue())),)
            output_str = output_stream.getvalue()
            if output_str:
                owin = OutputWindow(output_str)
                owin.show_all()
        except:
            _logger.debug("caught exception executing", exc_info=True)
            owin = OutputWindow(traceback.format_exc())
            owin.show_all()
            
    def __outln(self, stream, v):
        stream.write(str(v))
        stream.write('\n')
