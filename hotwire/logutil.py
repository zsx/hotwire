import sys, logging, logging.config, StringIO

def log_except(logger=None, text=''):
    def annotate(func):
        def _exec_cb(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                log_target = logger or logging
                log_target.exception('Exception in callback%s', text and (': '+text) or '')
        return _exec_cb
    return annotate

def init(default_level, debug_modules, prefix=None):
    rootlog = logging.getLogger() 
    fmt = logging.Formatter("%(asctime)s [%(thread)d] %(name)s %(levelname)s %(message)s",
                            "%H:%M:%S")
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    
    rootlog.setLevel(default_level)
    rootlog.addHandler(stderr_handler)
    for logger in [logging.getLogger(prefix+x) for x in debug_modules]:
        logger.setLevel(logging.DEBUG)

    logging.debug("Initialized logging")
