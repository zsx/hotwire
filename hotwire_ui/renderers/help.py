import StringIO

import gobject

from hotwire_ui.render import ClassRendererMapping
from hotwire_ui.renderers.unicode import UnicodeRenderer
from hotwire.builtin import BuiltinRegistry
from hotwire.builtins.help import HelpItem
from hotwire.version import __version__

class HelpItemRenderer(UnicodeRenderer):
    def __init__(self, context, **kwargs):
        super(HelpItemRenderer, self).__init__(context, monospace=False, **kwargs)
        self._buf.set_property('text', '')
        self._buf.insert_markup('Hotwire <i>%s</i>\n\n' % (__version__,))
        self._buf.insert_markup('New to hotwire? ')
        self.append_link('View Tutorial', 'http://hotwire-shell.org/trac/wiki/GettingStarted')
        self._buf.insert_markup('\n\n')
        self._buf.insert_markup('<larger>Important Keybindings:</larger>\n')
        self._buf.insert_markup('  <b>TAB</b> and <b>Shift-TAB</b> - Choose completions\n')
        self._buf.insert_markup('  <b>Up/Down</b> - Search history\n')
        self._buf.insert_markup('  <b>Ctrl-1</b>, <b>Ctrl-2</b>, ... or <b>Ctrl-PageUp</b> and <b>Ctrl-PageDown</b> - Switch tabs\n')
        self._buf.insert_markup('\n')
        self._buf.insert_markup('  See the menu for other keybindings.\n')
        self._buf.insert_markup('\n')
        self._buf.insert_markup('  The entry accepts Emacs/readline style input; for example:\n')
        self._buf.insert_markup('  <b>Ctrl-a</b> and <b>Ctrl-e</b> - Beginning/end of line\n')
        self._buf.insert_markup('\n')

        self._buf.insert_markup('<larger>Builtin Commands:</larger>\n')
        builtins = list(BuiltinRegistry.getInstance())
        builtins.sort(lambda a,b: cmp(a.name, b.name))
        for builtin in builtins:
            self._buf.insert_markup('  <b>%s</b> - in%s: <i>%s</i> out: <i>%s</i>\n' \
                                    % (builtin.name,
                                       builtin.get_input_optional() and ' (opt)' or '',
                                       gobject.markup_escape_text(str(builtin.get_input_type())),
                                       gobject.markup_escape_text(str(builtin.get_output_type()))))
            if builtin.__doc__:
                for line in StringIO.StringIO(builtin.__doc__):
                    self._buf.insert_markup('    ' + gobject.markup_escape_text(line))
                self._buf.insert_markup('\n')

    def get_status_str(self):
        return ''

    def append_obj(self, o):
        pass

    def get_autoscroll(self):
        return False
    
    def supports_input(self):
        return False

ClassRendererMapping.getInstance().register(HelpItem, HelpItemRenderer)
