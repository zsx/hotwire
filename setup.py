# -*- tab-width: 4; indent-tabs-mode: nil -*-

import os,sys

from hotwire.version import __version__

from distutils.core import setup

def svn_info(wd):
    import subprocess,StringIO
    tip = {}
    for line in StringIO.StringIO(subprocess.Popen(['svn', 'info', wd], stdout=subprocess.PIPE).communicate()[0]):
        line = line.strip()
        if not line:
            continue
        (k,v) = line.split(':', 1)
        tip[k.strip()] = v.strip()
    return tip

def svn_dist():
    import subprocess,tempfile
    import shutil

    dt = os.path.join('dist', 'test')
    try:
        os.mkdir('dist')
    except OSError, e:
        pass
    if os.path.exists(dt):
        shutil.rmtree(dt)
    subprocess.call(['svn', 'export', '.', dt])
    oldwd = os.getcwd()
    os.chdir(dt)
    verfile = open(os.path.join('hotwire', 'version.py'), 'a')
    verfile.write('\n\n##AUTOGENERATED by setup.py##\nsvn_version_info = %s\n' % (repr(svn_info(oldwd)),))
    verfile.close()
    subprocess.call(['python', 'setup.py', 'sdist', '-k', '--format=zip'])

def svn_dist_test():
    import subprocess
    svn_dist()
    os.chdir('hotwire-' + __version__)
    subprocess.call(['python', os.path.join('ui', 'test-hotwire')])

if 'svn-dist' in sys.argv:
    svn_dist()
    sys.exit(0)
elif 'svn-dist-test' in sys.argv:
    svn_dist_test()
    sys.exit(0)

kwargs = {}

if 'py2exe' in sys.argv:
    import py2exe
    kwargs['windows'] = [{'script': 'ui/hotwire', #'icon_resources': [(1, 'hotwire.ico')]
                        }]
    kwargs['options'] = {'py2exe': {'packages': 'encodings',
                                    'includes': 'cairo, pango, pangocairo, atk, gobject'}
                         }
else:
    kwargs['scripts'] = ['ui/hotwire', 'ui/hotwire-editor']
    kwargs['data_files'] = [('share/applications', ['hotwire.desktop']), ('share/icons/hicolor/24x24/apps', ['hotwire.png'])]

setup(name='hotwire',
      version=__version__,
      description='Hotwire Shell',
      author='Colin Walters',
      author_email='walters@verbum.org',
      url='http://hotwire-shell.org',
      packages=['hotwire', 'hotwire_ui', 'hotwire_ui.renderers', 'hotwire.builtins',
                'hotwire.pycompat', 'hotwire.sysdep', 'hotwire.sysdep.fs_impl', 
                'hotwire.sysdep.proc_impl',
                'hotwire.sysdep.term_impl', 'hotwire.sysdep.ipc_impl'],
      **kwargs)
