# This file is part of the Hotwire Shell project API.

# Copyright (C) 2007 Colin Walters <walters@verbum.org>

# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies 
# of the Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all 
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE 
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR 
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os,sys,subprocess,logging

import gtk

from hotwire.logutil import log_except
from hotwire.externals.singletonmixin import Singleton
from hotwire.externals.dispatch import dispatcher

_logger = logging.getLogger('hotwire.ui.adaptors.Editors')

class Editor(object):
    """Abstract superclass of external editors."""
    uuid = property(lambda self: self._uuid, doc="""Unique identifer for this editor.""")
    name = property(lambda self: self._name, doc="""Human-readable name for the editor.""")
    icon = property(lambda self: self._icon, doc="""Icon name for this editor; may be absolute or stock.""")
    executable = property(lambda self: self._executable, doc="""Executable program, may be a path.""")
    args = property(lambda self: self._args, doc="""Default arguments for program.""")
    requires_terminal = property(lambda self: self._requires_terminal, doc="""Whether or not this program should be run in a terminal.""")
    goto_line_arg_prefix = property(lambda self: self._goto_line_arg, doc="""Prefix argument required to jump to a specific line number.""")
    goto_line_arg = property(lambda self: self._goto_line_arg, doc="""Full argument required to jump to a specific line number.""")    
    
    def __init__(self, uuid, name, icon, executable, args=[]):
        super(Editor, self).__init__()
        self._uuid = uuid
        self._name = name
        self._icon = icon
        self._executable = executable
        self._args = args        
        self._requires_terminal = False
        self._goto_line_arg_prefix = '+'
        self._goto_line_arg = None
        
    def _get_startup_env(self):
        env = dict(os.environ)
        env['DESKTOP_STARTUP_ID'] = 'hotwire%d_TIME%d' % (os.getpid(), gtk.get_current_event_time(),)
        return env
    
    @log_except(_logger)
    def __idle_run_cb(self, cb):
        cb()
        return False
        
    def run_with_callback(self, cwd, file, callback, lineno=-1):
        args = [self.executable]
        if lineno >= 0:
            if self.goto_line_arg_prefix:
                args.append('%s%d', self.goto_line_arg_prefix, lineno)
            elif self.goto_line_arg:
                args.extend([self.goto_line_arg, '%d' % (lineno,)])
        args.append(file)
        if not self.requires_terminal:
            proc = subprocess.Popen(args, env=self._get_startup_env(), cwd=cwd)
            gobject.child_watch_add(proc.pid, self.__idle_run_cb, callback)
        else:
            # TODO - use hotwire-runtty ?
            raise NotImplementedError("Can't run terminal editors currently")

class EditorRegistry(Singleton):
    """Registry for supported external editors."""
    def __init__(self):
        self.__editors = {} # uuid->editor
        
    def __getitem__(self, uuid):
        return self.__editors[uuid]
        
    def __iter__(self):
        for x in self.__editors.itervalues():
            yield x

    def register(self, editor):
        if editor.uuid in self.__editors:
            raise ValueError("Editor uuid %s already registered", editor.uuid)
        self.__editors[editor.uuid] = editor
        dispatcher.send(sender=self)

class HotwireEditor(Editor):
    def __init__(self):
        super(HotwireEditor, self).__init__('c5851b9c-2618-4078-8905-13bf76f0a94f', 'Hotwire', 'hotwire-editor', 
                                            'hotwire.png', args=['--code'])
EditorRegistry.getInstance().register(HotwireEditor())    
        
class GVimEditor(Editor):
    def __init__(self):
        super(GVimEditor, self).__init__('eb88b728-42d1-4dc0-a20b-c885497520a2', 'GVim', 'gvim', 'gvim.png')
EditorRegistry.getInstance().register(GVimEditor())
