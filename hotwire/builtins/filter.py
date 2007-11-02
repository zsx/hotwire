import re

from hotwire.text import MarkupText
from hotwire.builtin import Builtin, BuiltinRegistry, InputStreamSchema

class StringMatch(MarkupText):
    def __new__(cls, value, match):
        inst = super(StringMatch, cls).__new__(cls, value)
        inst.match = match
        inst.add_markup('b', match.start(), match.end())
        return inst

class FilterBuiltin(Builtin):
    """Filter input objects by regular expression, matching on a property (or stringification)"""
    def __init__(self):
        super(FilterBuiltin, self).__init__('filter',
                                            input=InputStreamSchema('any'),
                                            output='identity',
                                            options=['-i', '--ignore-case'],
                                            threaded=True)

    def execute(self, context, regexp, prop=None, options=[]):
        if prop and prop[-2:] == '()':
            target_prop = prop[:-2]
            is_func = True
        else:
            target_prop = prop
            is_func = False
        compiled_re = re.compile(regexp, (('-i' in options) and re.IGNORECASE or 0) | re.UNICODE)
        for arg in context.input:
            target_propvalue = target_prop and getattr(arg, target_prop) or (isinstance(arg, str) and arg or str(arg))
            if is_func:
                target_propvalue = target_propvalue()
            match = compiled_re.search(target_propvalue)
            if match:
                if isinstance(arg, str):
                    yield StringMatch(target_propvalue, match)
                else:
                    yield arg
BuiltinRegistry.getInstance().register(FilterBuiltin())
