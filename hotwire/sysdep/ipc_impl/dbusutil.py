import dbus, dbus.glib

def bus_proxy(bus=None):
    target_bus = bus or dbus.Bus()
    return target_bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')

class DBusNameExistsException(Exception):
    pass

def take_name(name, replace=False, on_name_lost=None, bus=None):
    target_bus = bus or dbus.Bus()
    proxy = bus_proxy(bus=target_bus)
    flags = 1 | 4 # allow replacement | do not queue
    if replace:
        flags = flags | 2 # replace existing
    if not proxy.RequestName(name, dbus.UInt32(flags)) in (1,4):
        raise DBusNameExistsException("Couldn't get D-BUS name %s: Name exists")
    if on_name_lost:
        proxy.connect_to_signal('NameLost', on_name_lost)
