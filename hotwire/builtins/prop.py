import re

from hotwire.text import MarkupText
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema, OutputStreamSchema


class PropBuiltin(Builtin):
    """Return the property of an object"""
    def __init__(self):
        super(PropBuiltin, self).__init__('prop',
                                          input=InputStreamSchema('any'),
                                          output=OutputStreamSchema('any'),
                                          idempotent=True)

    def execute(self, context, prop):
        if prop[-2:] == '()':
            target_prop = prop[:-2]
            is_func = True
        else:
            target_prop = prop
            is_func = False
        for arg in context.input:
            target_propvalue = getattr(arg, target_prop)
            if is_func:
                target_propvalue = target_propvalue()
            yield target_propvalue
BuiltinRegistry.getInstance().register(PropBuiltin())
