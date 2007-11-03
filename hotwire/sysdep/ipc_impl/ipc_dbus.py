# -*- tab-width: 4 -*-
import os,sys,platform,logging

import gtk, dbus, dbus.service

import hotwire.sysdep.ipc_impl.dbusutil as dbusutil

_logger = logging.getLogger("hotwire.sysdep.Ipc.DBus")

BUS_NAME = 'org.hotwireshell'
UI_OPATH = '/hotwire/ui'
UI_IFACE = BUS_NAME + '.Ui'

class Ui(dbus.service.Object):
    def __init__(self, factory, bus_name):
        super(Ui, self).__init__(bus_name, UI_OPATH)
        self.__winfactory = factory
        pass

    @dbus.service.method(UI_IFACE,
                         in_signature="i")
    def NewWindow(self, timestamp):
        _logger.debug("Handling NewWindow method invocation (timestamp=%s)", timestamp)
        newwin = self.__winfactory.create_window()
        if timestamp > 0:
            newwin.present_with_time(timestamp)
        else:
            newwin.present()
            
    @dbus.service.method(UI_IFACE,
                         in_signature="as")            
    def RunTtyCommand(self, args):
        win = self.__winfactory.get_active_window()
        raise NotImplementedError()

class IpcDBus(object):
    def __init__(self):
        self.__uiproxy = None

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
        self.__uiproxy = Ui(win.factory, bus_name)

    def new_window(self):
        inst = dbus.SessionBus().get_object(BUS_NAME, UI_OPATH)
        inst_iface = dbus.Interface(inst, UI_IFACE)
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
            
    def run_tty_command(self, *args):
        inst = dbus.SessionBus().get_object(BUS_NAME, UI_OPATH)
        inst_iface = dbus.Interface(inst, UI_IFACE)
        inst.RunTtyCommand(*args)        

def getInstance():
    return IpcDBus()
