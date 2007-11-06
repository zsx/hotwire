import os,sys

from hotwire.cmdalias import AliasRegistry

default_aliases = {'vi': 'term vi',
                   'vim': 'term vim',
                   'ssh': 'term ssh',
                   'man': 'term man',
                   'info': 'term info',
                   'top': 'term top',
                   'nano': 'term nano',
                   'pico': 'term pico',
                   'irssi': 'term irssi',
                   'mutt': 'term mutt',
                  }
aliases = AliasRegistry.getInstance()
for name,value in default_aliases.iteritems():
    aliases.insert(name, value)

# This is a hack until we properly support command input in some way.
if os.path.exists('/usr/bin/gksudo'):
    aliases.insert('sudo', 'sh /usr/bin/gksudo --')


    