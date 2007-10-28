import os,sys,re
_pathexts = os.environ.get('PATHEXT', '.com;.exe;.bat').split(';')
_win_exec_re_str = '(' + ('|'.join(map(lambda x: '(' + re.escape(x) + ')', _pathexts))) + ')$'
win_exec_re = re.compile(_win_exec_re_str, re.IGNORECASE)
# Better suggestions accepted!  This is used to try to find the entrypoint for a process.
win_dll_re = re.compile(r'\.((dll)|(DLL)|(drv)|(DRV))$')
