import os, sys, logging, StringIO, traceback

import cairo, gtk, gobject, pango

try:
    import gtksourceview
    gtksourceview_avail = True
except ImportError, e:
    gtksourceview_avail = False

class ReallyBasicShell(gtk.VBox):
    def __init__(self, histpath=None, locals={}):
        super(ReallyBasicShell, self).__init__()

        self._locals = locals
        
        self._history_path = histpath
                                          
        self._save_text_id = 0        
        
        paned = gtk.VPaned()
        self.output = gtk.TextBuffer()
        self.output_view = gtk.TextView(self.output)
        self.output_view.set_wrap_mode(gtk.WRAP_WORD)
        self.output_view.set_property("editable", False)
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
        scroll.add(self.output_view)
        paned.pack1(scroll, True, True)

        if gtksourceview_avail:
            self.input = gtksourceview.SourceBuffer()
            pylang = gtksourceview.SourceLanguagesManager().get_language_from_mime_type("text/x-python")
            self.input.set_language(pylang)
            self.input.set_highlight(True)
            self.input_view = gtksourceview.SourceView(self.input)
        else:
            self.input = gtk.TextBuffer()
            self.input_view = gtk.TextView(self.input)
        self.input_view.set_wrap_mode(gtk.WRAP_WORD)        
        self.input.connect("changed", self._handle_text_changed)
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)        
        scroll.add(self.input_view)        
        paned.pack2(scroll, True, True)
        
        self.pack_start(paned, True, True)
        
        eval_button = gtk.Button("Eval")
        eval_button.connect("clicked", self.do_eval)
        self.pack_start(eval_button, False)

        try:
            history = file(self._history_path).read()
            self.input.set_property("text", history)
        except IOError, e:
            pass

    def _idle_save_text(self):
        history_file = file(self._history_path, 'w+')
        text = self.input.get_property("text")
        history_file.write(text)
        history_file.close()
        self._save_text_id = 0
        return False
    
    def _handle_text_changed(self, text):
        if self._save_text_id == 0:
            self._save_text_id = gobject.timeout_add(3000, self._idle_save_text)
    
    def do_eval(self, entry):
        try:
            output_stream = StringIO.StringIO()
            text = self.input.get_property("text")
            code_obj = compile(text, '<input>', 'exec')
            locals = {}
            for k, v in self._locals.items():
                locals[k] = v
            locals['output'] = output_stream
            exec code_obj in locals
            logging.debug("execution complete with %d output characters" % (len(output_stream.getvalue())),)
            self.output.set_property("text", output_stream.getvalue())
        except:
            logging.debug("caught exception executing")
            self.output.set_property("text", traceback.format_exc())

class CommandShell(gtk.Window):
    """Every application needs a development shell."""
    def __init__(self, locals={}, histpath=None):
        gtk.Window.__init__(self, type=gtk.WINDOW_TOPLEVEL)
        
        self.add(ReallyBasicShell(locals=locals, histpath=histpath))
        self.set_size_request(400, 600)
    
