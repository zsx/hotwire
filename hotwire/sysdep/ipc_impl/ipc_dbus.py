# -*- tab-width: 4 -*-
import os,sys,platform,logging

import gtk, dbus, dbus.service

import hotwire.sysdep.ipc_impl.dbusutil as dbusutil

_logger = logging.getLogger("hotwire.sysdep.Ipc.DBus")

BUS_NAME = 'org.verbum.Hotwire'
WINDOW_OPATH = '/hotwire/window'
WINDOW_IFACE = BUS_NAME + '.Window'

class Window(dbus.service.Object):
    def __init__(self, srcwin, bus_name):
        super(Window, self).__init__(bus_name, WINDOW_OPATH)
        self.__srcwin = srcwin
        pass

    @dbus.service.method(WINDOW_IFACE,
                         in_signature="i")
    def NewWindow(self, timestamp):
        _logger.debug("Handling NewWindow method invocation (timestamp=%s)", timestamp)
        newwin = self.__srcwin.factory.create_window()
        if timestamp > 0:
            newwin.present_with_time(timestamp)
        else:
            newwin.present()

class IpcDBus(object):
    def __init__(self):
        self.__winproxy = None

    def singleton(self):
        try:
            _logger.debug("Requesting D-BUS name %s on session bus", BUS_NAME)
            dbusutil.take_name(BUS_NAME, bus=dbus.SessionBus())
        except dbusutil.DBusNameExistsException, e:
            return True
        return False

    def register_window(self, win):
        _logger.debug("Registering window object %s", win)
        bus_name = dbus.service.BusName(BUS_NAME, bus=dbus.SessionBus())
        self.__winproxy = Window(win, bus_name)

    def new_window(self):
        inst = dbus.SessionBus().get_object(BUS_NAME, WINDOW_OPATH)
        inst_iface = dbus.Interface(inst, WINDOW_IFACE)
        _logger.debug("Sending RaiseNoTimestamp to existing instance")
        try:
            startup_time = None
            try:
                startup_id_env = os.environ['DESKTOP_STARTUP_ID']
            except KeyError, e:
                startup_id_env = None
            if startup_id_env:
                idx = startup_id_env.find('_TIME')
                if idx > 0:
                    idx += 5
                    startup_time = int(startup_id_env[idx:])
            if startup_time:
                inst_iface.NewWindow(startup_time) 
            else:
                inst_iface.NewWindow(0)
        except dbus.DBusException, e:
            _logger.error("Caught exception attempting to send RaiseNoTimestamp", exc_info=True)

def getInstance():
    return IpcDBus()
