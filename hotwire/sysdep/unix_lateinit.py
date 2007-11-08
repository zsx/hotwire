import os,sys

from hotwire.cmdalias import AliasRegistry

default_aliases = {'sudo': 'term sudo',
                   'vi': 'term vi',
                   'vim': 'term vim',
                   'ssh': 'term ssh',
                   'man': 'term man',
                   'info': 'term info',
                   'less': 'term less',
                   'more': 'term more',  
                   'top': 'term top',
                   'powertop': 'term powertop',                   
                   'nano': 'term nano',
                   'pico': 'term pico',
                   'irssi': 'term irssi',
                   'mutt': 'term mutt',
                  }
aliases = AliasRegistry.getInstance()
for name,value in default_aliases.iteritems():
    aliases.insert(name, value)
