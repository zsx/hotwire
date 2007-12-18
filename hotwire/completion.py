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

import os,sys,re,stat,logging
import posixpath

import gobject

import hotwire
from hotwire.builtin import BuiltinRegistry
from hotwire.cmdalias import Alias, AliasRegistry
from hotwire.async import MiniThreadPool
from hotwire.fs import FilePath,iterd,iterd_sorted,path_normalize,path_expanduser,unix_basename
from hotwire.sysdep.fs import Filesystem
from hotwire.singletonmixin import Singleton
from hotwire.util import quote_arg, tracefn
from hotwire.state import UsageRecord, History
from hotwire.sysdep.fs import Filesystem

_logger = logging.getLogger("hotwire.Completion")

class Completion(object):
    """Represents a match of a string by some text input."""
    __slots__ = ['suffix', 'target', 'matchbase']
    def __init__(self, 
                  suffix,
                  target,
                  matchbase):
        self.suffix = suffix
        self.matchbase = matchbase
        self.target = target

    def __cmp__(self, other):
        return cmp(self.suffix,other.suffix)

class Completer(object):
    def __init__(self):
        super(Completer, self).__init__()
        
    def _match(self, name, text, target):
        if name.startswith(text):
            return Completion(name[len(text):], target, name)
        return None

def _mkfile_completion(text, fpath, fileobj=None):
    fs = Filesystem.getInstance()
    fname = unix_basename(fpath)
    if text.endswith('/'):
        textbase = ''
    else:
        textbase = unix_basename(text)
    fobj = fileobj or fs.get_file_sync(fpath)
    startidx = fpath.rindex(fname)
    suffix = fpath[startidx+len(textbase):]
    if fobj.is_directory(follow_link=True):
        suffix += '/'
    return Completion(suffix, fobj, fname)     

class PathCompleter(Completer):
    def __init__(self):
        super(PathCompleter, self).__init__()

    def completions(self, text, cwd):
        textpath = FilePath(text, cwd)
        fullpath = path_expanduser(textpath)
        try:
            isdir = stat.S_ISDIR(os.stat(srcpath).st_mode)
        except:
            isdir = False
        fs = Filesystem.getInstance()
        if isdir and fullpath.endswith('/'):
            for fpath in iterd_sorted(fullpath, fpath=True):
                yield _mkfile_completion(text, fpath)
            return
        (src_dpath, src_prefix) = os.path.split(fullpath)
        try:
            for fpath in iterd_sorted(src_dpath, fpath=True):
                fname = unix_basename(fpath)
                if fname.startswith(src_prefix):
                    try:
                        yield _mkfile_completion(text, fpath)
                    except OSError, e:
                        pass
        except OSError, e:
            pass

class BuiltinCompleter(Completer):
    def __init__(self):
        super(BuiltinCompleter, self).__init__()

    def completions(self, text, cwd, context=None):
        for builtin in BuiltinRegistry.getInstance():
            compl = self._match(builtin.name, text, builtin)
            if compl: yield compl
            for alias in builtin.aliases:
                compl = self._match(alias, text, builtin)
                if compl: yield compl

class VerbCompleter(Completer):
    def __init__(self):
        super(VerbCompleter, self).__init__()

    def completions(self, text, cwd, context=None):
        bc = BuiltinCompleter()
        for completion in bc.completions(text, cwd, context=context):
            yield completion
        aliases = AliasRegistry.getInstance()
        for alias in aliases:
            compl = self._match(alias.name, text, alias)
            if compl: yield compl
        if text.find('/') >= 0 or text.startswith('.' + os.sep):
            pc = PathCompleter()
            for completion in pc.completions(text, cwd):
                fobj = completion.target
                if fobj.is_directory() or fobj.is_executable():
                    yield completion
        else:
            fs = Filesystem.getInstance()
            for dpath in fs.get_path_generator():
                if not os.access(dpath, os.X_OK):
                    continue
                for fpath in iterd_sorted(dpath):
                    fname = unix_basename(fpath)
                    if not fname.startswith(text):
                        continue
                    fobj = fs.get_file_sync(fpath)
                    if fobj.is_executable():
                        yield _mkfile_completion(text, fpath, fobj)

class TokenCompleter(Completer):
    def __init__(self):
        super(TokenCompleter, self).__init__()

    def completions(self, text, cwd):
        pathcompleter = PathCompleter()
        for completion in pathcompleter.completions(text, cwd):
            yield completion

class CompletionResults(object):
    def __init__(self, resultlist):
        super(CompletionResults, self).__init__()
        self.results = resultlist
        self.common_prefix = self.__get_common_prefix(self.results)
 
    def __get_common_prefix(self, completions):
        if len(completions) <= 1:
            return None
        min_item = completions[0]
        max_item = completions[-1]
        n = min(len(min_item.suffix), len(max_item.suffix))
        for i in xrange(n):
            if min_item.suffix[i] != max_item.suffix[i]:
                return min_item.suffix[:i]
        return min_item.suffix[:n]       
    
class CompletionSystem(object):
    def __init__(self):
        self.__completion_ids = 0
        
    def sync_complete(self, *args):
        return self.__get_completions(*args)

    def async_complete(self, *args):
        return MiniThreadPool.getInstance().run(self.__do_async_complete, args=args)
    
    def __get_completions(self, completer, text, cwd):
        return CompletionResults(list(completer.completions(text, cwd)))

    def __do_async_complete(self, completer, text, cwd, cb):
        result = self.__get_completions(completer, text, cwd)
        def do_cb(*args):
            cb(*args)
            return False
        gobject.idle_add(do_cb, completer, text, result)
