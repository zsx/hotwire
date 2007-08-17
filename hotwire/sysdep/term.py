# -*- tab-width: 4 -*-
import sys,os,logging

import hotwire.sysdep.term_impl

_logger = logging.getLogger("hotwire.sysdep.Terminal")
_module = None
try:
    import hotwire.sysdep.term_impl.term_vte
    _module = hotwire.sysdep.term_impl.term_vte
except ImportError, e:
    _logger.debug("Failed to import vte", exc_info=True)

_instance = None
class Terminal(object):
    @staticmethod
    def getInstance():
        global _instance
        if _instance is None:
            if not _module:
                raise NotImplementedError("Couldn't find a terminal implementation")
            _instance = _module.getInstance()
        return _instance
