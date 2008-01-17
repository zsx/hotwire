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
        
        
        (fd, fpath) = tempfile.mkstemp('.py', 'script', scriptdir)
        shasum = sha.new()
        if context.input_type is not None:
            content = self.PYCMD_WITHINPUT_CONTENT % (context.input_type,)
        else:
            content = self.PYCMD_NOINPUT_CONTENT
        f = os.fdopen(fd, 'w')
        shasum.update(content)
        f.write(content)
        f.close()
        sum_hex = shasum.hexdigest()
        retval = subprocess.call([os.environ['EDITOR'], fpath], cwd=context.cwd, close_fds=True)
        buf = open(fpath).read()
        new_sum = sha.new()        
        new_sum.update(buf)
        new_sum_hex = new_sum.hexdigest() 
        if new_sum_hex == sum_hex:
            os.unlink(fpath)
            raise ValueError(_("Script not modified, aborting"))
        new_fpath = os.path.join(scriptdir, new_sum_hex+'.py')
        os.rename(fpath, new_fpath)        

BuiltinRegistry.getInstance().register(PyMapBuiltin())
