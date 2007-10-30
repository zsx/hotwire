import os,sys

from hotwire.cmdalias import AliasRegistry

# This is a hack until we properly support command input in some way.
if os.path.exists('/usr/bin/gksudo'):
    AliasRegistry.getInstance().insert('sudo', 'sh /usr/bin/gksudo --')
    