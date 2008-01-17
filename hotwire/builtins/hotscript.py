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

import os,sys,re,subprocess,sha,tempfile,uuid

from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema
from hotwire.command import PipelineLanguageRegistry

from hotwire.fs import path_join
from hotwire.sysdep.fs import Filesystem

class HotScriptBuiltin(Builtin):
    __doc__ = _("""Create and run a script file.""")
 
    def __init__(self):
        super(HotScriptBuiltin, self).__init__('hotscript',
                                               threaded=True,
                                               input=InputStreamSchema('any', optional=True),
                                               output=OutputStreamSchema('any'),
                                               options=[['-n', '--new'],['-p','--pipe']])

    def execute(self, context, args, options=[]):
        if len(args) > 1:
            raise ValueError(_("Too many arguments specified"))
        if len(args) < 1:
            raise ValueError(_("Too few arguments specified"))
        lang_uuid = args[0]
        
        lang = PipelineLanguageRegistry.getInstance()[lang_uuid]
                
        fs = Filesystem.getInstance()
        scriptdir = fs.make_conf_subdir('scripts')
        i = 0
        while True:
            i += 1
            if i > 10:
                raise ValueError("Couldn't create new script file")
            uuidobj = uuid.uuid4()
            uuid_fname = str(uuidobj) + lang.fileext
            uuid_path = path_join(scriptdir, uuid_fname)
            if not os.path.exists(uuid_path):
                break
        
        f = open(uuid_path, 'w')
        if lang.script_content:
            orig_shasum = sha.new()
            orig_shasum.update(lang.script_content)            
            f.write(lang.script_content)
        else:
            orig_shasum = None
        f.close()
        
        editor = EditorRegistry.getInstance().get_preferred()
        retcode = editor.run_sync(f, lineno=lang.script_content_line)
        if retcode != 0:
            os.unlink(uuid_path)
            raise ValueError(_("Editor aborted"))
        f = open(uuid_path)
        new_shasum = sha.new()
        new_shasum.update(f.read())
        f.close()
        
        if new_shasum.hexdigest() == orig_shasum.hexdigest():
            os.unlink(uuid_path)
            raise ValueError(_("Input unchanged, aborting"))
        
        
BuiltinRegistry.getInstance().register(PyMapBuiltin())
