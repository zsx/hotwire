import os,sys

import hotwire
from hotwire.singletonmixin import Singleton

class ObjectStreamSchema(object):
    def __init__(self, otype, name=None, opt_formats=[]):
        self.otype = otype
        self.name = name
        self.opt_formats = opt_formats

class InputStreamSchema(ObjectStreamSchema):
    def __init__(self, otype, optional=False, **kwargs):
        super(InputStreamSchema, self).__init__(otype, **kwargs)
        self.optional = optional

class OutputStreamSchema(ObjectStreamSchema):
    def __init__(self, otype, merge_default=False, typefunc=None, **kwargs):
        super(OutputStreamSchema, self).__init__(otype, **kwargs)
        self.merge_default = merge_default
        self.typefunc = typefunc

def undoable():
    def annotate(f):
        setattr(f, 'hotwire_undoable', True)
        return f
    return annotate

def idempotent():
    def annotate(f):
        setattr(f, 'hotwire_idempotent', True)
        return f
    return annotate

class HotwireBuiltinArg(object):
    def __init__(self, t, optional, completer_class=None):
        self.argtype = t
        self.optional = optional
        self.completer_class = completer_class

def parseargs(ct):
    if not ct in ('ws-tokenize', 'str', 'shglob', 'str-shquoted'):
        raise ValueError('Bad parseargs: %s' % (ct,))
    def annotate(f):
        setattr(f, 'hotwire_parseargs', ct)
        return f
    return annotate

def argtypes(*args):
    def annotate(f):
        arg_objs = []
        func_arg_count = len(f.func_code.co_varnames)
        func_opt_count = f.func_defaults and len(f.func_defaults) or 0
        func_req_count = func_arg_count - func_opt_count
        if func_arg_count != len(args):
            raise TypeError("argtypes len %d doesn't match function argument count %d",
                            len(args), func_arg_count)
        for i,arg in enumerate(args):
            argval = arg
            completer = None
            if isinstance(arg, tuple):
                argval = arg[0]
                completer = arg[1]
            optional = i > func_arg_count
            arg_objs.append(HotwireBuiltinArg(arg, optional, completer))
        setattr(f, 'hotwire_arg_types', tuple(arg_objs))
        return f
    return annnotate

def options(*args):
    def annotate(f):
        setattr(f, 'hotwire_options', tuple(args))
        return f
    return annotate

def locality(locality):
    def annotate(f):
        setattr(f, 'hotwire_locality', locality)
        return f
    return annotate

def hasstatus():
    def annotate(f):
        setattr(f, 'hotwire_hasstatus', True)
        return f
    return annotate

def _attr_or_none(o, a):
    return hasattr(o, a) and getattr(o, a) or None

class Builtin(object):
    def __init__(self, name, 
                 input=None,
                 output=None,
                 outputs=[],
                 aliases=[], 
                 remote_only=False, 
                 nostatus=False):
        self.input=input
        self.outputs = output and [output] or outputs
        self.name = name
        self.aliases = aliases 
        self.remote_only = remote_only 
        self.nostatus = nostatus

    def get_completer(self, *args, **kwargs):
        return None

    def cancel(self, context):
        pass

    def execute(self, context, *args):
        raise NotImplementedError()

    def __get_exec_attr_or_none(self, attr):
        func = self.execute 
        return _attr_or_none(func, attr)

    def get_input(self):
        return self.input

    def get_outputs(self):
        return self.outputs

    def get_input_opt_formats(self):
        if self.input:
            return self.input.opt_formats
        return []
    
    def get_output_opt_formats(self):
        if self.outputs:
            return self.outputs[0].opt_formats
        return []

    def get_aux_outputs(self):
        return self.outputs[1:]

    def get_input_type(self):
        if self.input:
            return self.input.otype
        return None

    def get_input_optional(self):
        if self.input:
            return self.input.optional
        return False

    def get_output_type(self):
        if self.outputs:
            return self.outputs[0].otype
        return None

    def get_output_typefunc(self):
        if self.outputs:
            return self.outputs[0].typefunc
        return None

    def get_locality(self):
        return self.__get_exec_attr_or_none('hotwire_locality')

    def get_parseargs(self):
        return self.__get_exec_attr_or_none('hotwire_parseargs') or 'ws-parsed'

    def get_options(self):
        return self.__get_exec_attr_or_none('hotwire_options') or None 

    def get_idempotent(self):
        return self.__get_exec_attr_or_none('hotwire_idempotent') or False

    def get_undoable(self):
        return self.__get_exec_attr_or_none('hotwire_undoable') or False

    def get_hasstatus(self):
        return self.__get_exec_attr_or_none('hotwire_hasstatus') or False

class BuiltinRegistry(Singleton):
    def __init__(self):
        self.__builtins = set()

    def __getitem__(self, name):
        for x in self.__builtins:
            if x.name == name or name in x.aliases:
                return x
        raise KeyError(name)

    def __iter__(self):
        for x in self.__builtins:
            yield x

    def register(self, builtin):
        self.__builtins.add(builtin)

import hotwire.builtins.cat
import hotwire.builtins.cd
import hotwire.builtins.cp
import hotwire.builtins.filter
import hotwire.builtins.fsearch
import hotwire.builtins.help
import hotwire.builtins.history
import hotwire.builtins.last
import hotwire.builtins.ls
import hotwire.builtins.mv
import hotwire.builtins.open
import hotwire.builtins.prop
import hotwire.builtins.ps
import hotwire.builtins.rm
import hotwire.builtins.sh
import hotwire.builtins.term
#moddir = hotwire.ModuleDir(os.path.join(os.path.dirname(hotwire.__file__), 'builtins'))
#moddir.do_import()
