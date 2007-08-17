import sys, logging, logging.config, StringIO

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
