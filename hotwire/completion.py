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
from hotwire.cmdalias import AliasRegistry
from hotwire.generator import CompoundGenerator, GeneratorFilter, GeneratorPureFilter
from hotwire.fs import FilePath,DirectoryGenerator,path_normalize,path_expanduser
from hotwire.sysdep.fs import Filesystem
from hotwire.singletonmixin import Singleton
from hotwire.util import quote_arg, tracefn
from hotwire.state import UsageRecord, History
from hotwire.sysdep.fs import Filesystem

_logger = logging.getLogger("hotwire.Completion")

def _path_from_shterm(token):
    if token.startswith('sh '):
        return token[3:]
    elif token.startswith('term '):
        return token[5:]
    else:
        return token

class Completion(object):
    """Represents a match of an string by some text input."""
    def __init__(self, mstr, start, mlen,
                 hint_no_space=False,
                 exact=False,
                 ctxhit=False,
                 matchtarget=None,
                 default_icon=None):
        self.mstr = mstr
        self.start = start
        self.prefix = ''
        self.mlen = mlen
        self.hint_no_space = hint_no_space
        self.exact = exact
        self.ctxhit = ctxhit
        self.matchtarget = matchtarget
        self.typename = None
        self.default_icon = default_icon
        self._icon_cb = None 

    def set_prefix(self, prefix):
        self.prefix = prefix
    
    def append_prefix(self, prefix):
        self.prefix = (self.prefix or '') + prefix

    def remove_mstr_prefix(self, prefix):
        if self.mstr.startswith(prefix):
            pfxlen = len(prefix) 
            self.mstr = self.mstr[pfxlen:]
            self.start -= (pfxlen-1)
            return True
        return False
    
    def get_matchdata(self):
        if self.prefix:
            mstr = self.prefix + self.mstr
        else: 
            mstr = self.mstr
        pfxlen = len(self.prefix)
        return (mstr, self.start+pfxlen, self.mlen)
   
    def _base_cmp(self, other):
        if self.ctxhit and not other.ctxhit:
            return -1
        elif other.ctxhit:
            return 1
        elif self.exact and not other.exact:
            return -1
        elif other.exact:
            return 1
        return None

    def __cmp__(self, other):
        val = self._base_cmp(other)
        if val is not None:
            return val
        else:
            return cmp(self.mlen,other.mlen)

    def __str__(self):
        return "Completion of %s (%d %d %s%s)" % (self.mstr, self.start, self.mlen,
                                                  self.exact and 'exact ' or '',
                                                  self.ctxhit and 'ctxhit ' or '')

    def get_icon(self, context=None):
        return self.default_icon

    def set_icon_cb(self, cb):
        self._icon_cb = cb

class FilePathCompletion(Completion):
    def __init__(self, mstr, *args, **kwargs):
        super(FilePathCompletion, self).__init__(mstr, *args, **kwargs)
        self.fpath = mstr
        self.typename = 'File'
        self.__file = None

    def __get_icon(self):
        if self.__file:
            return Filesystem.getInstance().get_file_icon_name(self.__file) 
        return None

    def __signal_icon(self):
        if self._icon_cb:
            self._icon_cb(self)

    def get_icon(self, context=None):
        if not self.__file:
            path = FilePath(_path_from_shterm(self.mstr), context.get_cwd())
            self.__file = Filesystem.getInstance().get_file(path)
            self.__file.connect('changed', lambda f: self.__signal_icon())
        return self.__get_icon()

def _match(item, text):
    return (item.startswith(text), len(item) == len(text))

class BaseCompleter(object):
    def __init__(self, generator=None):
        self._generator = generator
        self.__ext_filters = []

    def _set_generator(self, generator):
        self._generator = generator

    def _get_generator(self, search=None):
        return self._generator

    def _match_substr(self):
        return False

    def add_filter(self, filter):
        self.__ext_filters.append(filter)

    def _make_compl(self, item, mstart, mlen, exact):
        return Completion(item, mstart, mlen, exact=exact)

    def _item_text(self, item):
        return item

    def _filter_item(self, item, text):
        itemtxt = self._item_text(item)
        if not self._match_substr():
            (match, exact) = _match(itemtxt, text)
            if match:
                return (True, self._make_compl(item, 0, len(text), exact=exact))
            return (False, None)
        else:
            idx = itemtxt.find(text)
            if idx < 0:
                return (False, None)
            return (True, self._make_compl(item, idx, len(text), exact=(idx==0)))

    def _ext_filter(self, item):
        for f in self.__ext_filters:
            if not f(item):
                return False
        return True

    def search(self, text, context=None, hotwire=None):
        gen = self._get_generator(search=text)
        _logger.debug("using generator: %s", gen)
        for item in gen:
            if not self._ext_filter(item):
                continue
            (is_match, result) = self._filter_item(item, text)
            if is_match:
                yield result

class CompletionProxy(object):
    def __init__(self, source):
        self.__source = source

    def mark_chosen(self, *args, **kwargs):
        self.__source.mark_chosen(*args, **kwargs)

    def search(self, *args, **kwargs):
        self.__source.search(*args, **kwargs)

class CompletionPrefixStripProxy(CompletionProxy):
    def __init__(self, source, prefix, addprefix=None):
        self.__source = source
        self.__prefix = prefix
        self.__addprefix = addprefix

    def search(self, *args, **kwargs):
        for item in self.__source.search(*args, **kwargs):
            if isinstance(item, FilePathCompletion):
                removed = item.remove_mstr_prefix(self.__prefix)
                if removed and self.__addprefix:
                    item.append_prefix(self.__addprefix)
                yield item
            else:
                yield item

class CompletionContext(object):
    def __init__(self, source):
        self.__source = source

    def get_common_prefix(self):
        if len(self.__sorted_items) <= 1:
            return None
        for item in self.__sorted_items:
            if item.start > 0:
                return None
        min_item = self.__sorted_items[0]
        max_item = self.__sorted_items[-1]
        n = min(len(min_item.mstr), len(max_item.mstr))
        for i in xrange(n):
            if min_item.mstr[i] != max_item.mstr[i]:
                return min_item.mstr[:i]
        return min_item.mstr[:n]

    def set_search(self, text, find_common_prefix=False, **kwargs):
        self.__sorted_items = sorted(self.__source.search(text, **kwargs))

    def search(self):
        for item in self.__sorted_items:
            yield item

def path_filter_item(path, input):
    (dirname, basename) = os.path.split(path)
    (match, exact) = _match(basename, input)
    if match: 
        return (True, FilePathCompletion(path, len(dirname)+1, len(input), exact=exact))
    return (False, None)

class PathCompleter(BaseCompleter):
    def __init__(self):
        super(PathCompleter, self).__init__(None)

    def search(self, text, hotwire=None, context=None, cwd=None):
        src_context = (hotwire and hotwire.context) or context
        assert src_context
        text = path_expanduser(text)
        (input_dname, input_fname) = os.path.split(text)
        input_dname = os.path.join(cwd or src_context.get_cwd(), input_dname)
        input_dname = path_normalize(input_dname)
        generator = []
        try:
            if stat.S_ISDIR(os.stat(input_dname).st_mode):
                _logger.debug("Creating directory generator for %s", input_dname)
                generator = DirectoryGenerator(input_dname)
        except:
            _logger.debug("Failed to stat %s", input_dname)
            generator = DirectoryGenerator(src_context.get_cwd())
        have_fcompletions = False
        for path in generator:
            if not self._ext_filter(path):
                continue
            _logger.debug("checking: %s", path)
            (dname, fname) = os.path.split(path)
            try:
                is_dir = stat.S_ISDIR(os.stat(path).st_mode)
            except:
                is_dir = False
            (match, exact) = _match(fname, input_fname)
            if match:
                if is_dir:
                    resultpath = FilePath(path + '/') # Always use / because we normpath where needed
                else:
                    resultpath = path
                have_fcompletions = True
                yield FilePathCompletion(resultpath, len(dname), len(input_fname),
                                         hint_no_space=True, exact=exact, ctxhit=True)

class DirExecutableGenerator(object):
    def __init__(self, dir, include_subdirs=False):
        self.dir = dir
        self.__include_subdirs = include_subdirs
        self.__x_filter = Filesystem.getInstance().get_executable_filter() 

    def __iter__(self):
        for elt in DirectoryGenerator(self.dir):
            fullpath = FilePath(elt, self.dir)
            if self.__include_subdirs:
                try:
                    stbuf = os.stat(fullpath)
                    if stat.S_ISDIR(stbuf.st_mode):
                        yield fullpath
                    elif self.__x_filter(fullpath, stbuf=stbuf):
                        yield fullpath
                except OSError, e:
                    continue
            elif self.__x_filter(fullpath):
                yield fullpath

class PathExecutableCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(PathExecutableCompleter, self).__init__('exec')
        gens = []
        for dir in Filesystem.getInstance().get_path_generator():
            if os.access(dir, os.R_OK):
                gens.append(DirExecutableGenerator(dir))
        self._set_generator(CompoundGenerator(gens))

    def _filter_item(self, path, input):
        return path_filter_item(path, input)

class CwdExecutableCompleter(object):
    def __init__(self, cwd):
        super(CwdExecutableCompleter, self).__init__()
        self.__cwd = cwd
        self.__generator = DirExecutableGenerator(cwd, include_subdirs=True)

    def search(self, text, context=None, hotwire=None):
        was_cwd = False
        dotslash = '.' + os.sep 
        if text.startswith(dotslash):
            text = text[2:]
            was_cwd = True
        for item in self.__generator:
            (is_match, result) = self._filter_item(item, text)
            if is_match:
                yield result

    def _filter_item(self, path, input):
        return path_filter_item(path, input)

class BuiltinCompletion(Completion):
    def __init__(self, *args, **kwargs):
        super(BuiltinCompletion, self).__init__(*args, **kwargs)
        self.typename = 'Builtin'

    def get_icon(self, context=None):
        return 'hotwire'

class BuiltinCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(BuiltinCompleter, self).__init__()
        self._set_generator(BuiltinRegistry.getInstance())

    def _filter_item(self, builtin, input):
        #if self._hotwire.remote_active() and builtin.remote_only:
        #    return (False, None)
        (match, exact) = _match(builtin.name, input)
        if match:
            return (True, BuiltinCompletion(builtin.name, 0, len(input), exact=exact))
        for elt in builtin.aliases:
            (match, exact) = _match(elt, input)
            if match:
                return (True, BuiltinCompletion(builtin.name, 0, len(input), exact=exact))
        return (False, None)

class AliasCompletion(Completion):
    def __init__(self, *args, **kwargs):
        super(AliasCompletion, self).__init__(*args, **kwargs)
        self.typename = 'Alias'

    def get_icon(self, context=None):
        return 'hotwire'

class AliasCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(AliasCompleter, self).__init__()
        self._set_generator(AliasRegistry.getInstance())

    def _filter_item(self, alias, input):
        (match, exact) = _match(alias, input)
        if match:
            aliasval = AliasRegistry.getInstance()[alias]
            return (True, AliasCompletion(aliasval, 0, len(input), exact=exact, matchtarget=alias))
        return (False, None)

class VerbCompleter(object):
    def __init__(self, cwd):
        super(VerbCompleter, self).__init__()
        self._history = History.getInstance()
        self.__cwd = cwd
        self._cwd_completer = CwdExecutableCompleter(cwd)

    def mark_chosen(self, token):
        # FIXME gross hack, need infrastructure for compound completers 
        if token in BuiltinGenerator():
            BuiltinCompleter.getInstance().mark_chosen(token)
        else:
            token = _path_from_shterm(token)
            PathExecutableCompleter.getInstance().mark_chosen(token)

    def __prefix_completion(self, item): 
        if os.path.basename(item.mstr) in self._history.get_autoterm_cmds():
            item.set_prefix('term ')
        else:
            item.set_prefix('sh ')

    def __dir_or_x(self, path):
        if Filesystem.getInstance().get_executable_filter()(path):
            return True
        try:
            stbuf = os.stat(path)
            return stat.S_ISDIR(stbuf.st_mode)
        except OSError, e:
            return False

    def search(self, text, context=None, hotwire=None):
        found_noncwd = False
        for item in BuiltinCompleter.getInstance().search(text):
            found_noncwd = True
            yield item
        for item in AliasCompleter.getInstance().search(text):
            found_noncwd = True
            yield item
        if text.find('/') >= 0 or text.startswith('.' + os.sep):
            pc = PathCompleter()
            pc.add_filter(self.__dir_or_x)
            for item in pc.search(text, context=context, hotwire=hotwire):
                found_noncwd = True
                self.__prefix_completion(item)
                yield item
        else:
            for item in PathExecutableCompleter.getInstance().search(text):
                found_noncwd = True
                self.__prefix_completion(item)
                yield item
        if not found_noncwd:
            for item in self._cwd_completer.search(text):
                self.__prefix_completion(item)
                yield item

class HistoryCompletion(Completion):
    def __init__(self, *args, **kwargs):
        if kwargs.has_key('freq'):
            freq = kwargs['freq']
            del kwargs['freq']
        else:
            freq = None 
        super(HistoryCompletion, self).__init__(*args, **kwargs)
        self.typename = 'History'
        self.freq = freq

    def __cmp__(self, other):
        if self.freq and isinstance(other, HistoryCompletion) and other.freq:
            return cmp(other.freq, self.freq)
        else:
            return super(HistoryCompletion, self).__cmp__(other)

    def get_icon(self, context=None):
        return 'gtk-copy'

class HistoryCompleter(BaseCompleter):
    def __init__(self, name, **kwargs):
        super(HistoryCompleter, self).__init__(**kwargs)
        self._history = History.getInstance()
        self._name = name

    def _get_generator(self, search=None):
        return self._history.search_usage(self._name, search)

    def _make_compl(self, item, mstart, mlen, exact):
        return HistoryCompletion(item[0], mstart, mlen, exact=exact, freq=item[1])

    def _item_text(self, item):
        return item[0]

class TokenHistoryCompleter(HistoryCompleter):
    def __init__(self):
        super(TokenHistoryCompleter, self).__init__('token')

    def _match_substr(self):
        return True

class TokenCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(TokenCompleter, self).__init__()

    def search(self, text, **kwargs):
        pathcompleter = PathCompleter()
        have_fcompletions = False
        for item in pathcompleter.search(text, **kwargs):
            have_fcompletions = True
            yield item
        if not have_fcompletions:
            tokens = TokenHistoryCompleter() 
            for item in tokens.search(text, **kwargs):
                yield item

class CwdHistoryCompleter(Singleton, HistoryCompleter):
    def __init__(self):
        super(CwdHistoryCompleter, self).__init__('dir')

    def _match_substr(self):
        return True

class CdCompleter(Singleton, BaseCompleter):
    def __init__(self):
        super(CdCompleter, self).__init__()
	
    def __dirfilter(self, path):
        try:
            return stat.S_ISDIR(os.stat(path).st_mode)
        except OSError, e:
            return False

    def search(self, text, **kwargs):
        completer = PathCompleter()
        completer.add_filter(self.__dirfilter)
        for result in completer.search(text, **kwargs):
            yield result
        history = CwdHistoryCompleter.getInstance()
        for result in history.search(text, **kwargs):
            yield result
