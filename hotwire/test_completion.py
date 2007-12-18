# This file is part of the Hotwire Shell project API.

# Copyright (C) 2007 Colin Walters <walters@verbum.org>

# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies 
# of the Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all 
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE 
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR 
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os, sys, unittest, tempfile, shutil, platform

import hotwire
from hotwire.fs import path_join
from hotwire.completion import *
from hotwire.sysdep import is_windows, is_unix

class CompletionTests(unittest.TestCase):
    def setUp(self):
        self._tmpd = None
        self.vc = VerbCompleter()
        self.tc = TokenCompleter()
        self.pc = PathCompleter()        

    def tearDown(self):
        if self._tmpd:
            shutil.rmtree(self._tmpd)

    def _setupTree1(self):
        self._tmpd = tempfile.mkdtemp(prefix='hotwiretest')
        os.mkdir(path_join(self._tmpd, 'testdir'))
        if is_unix(): 
            self._test_exe_path = path_join(self._tmpd, 'testf')
            open(self._test_exe_path, 'w').close()
            os.chmod(self._test_exe_path, 744)
        elif is_windows():
            self._test_exe_path = path_join(self._tmpd, 'testf.exe')
            open(self._test_exe_path, 'w').close()
        os.mkdir(path_join(self._tmpd, 'dir with spaces'))

    def _setupTree2(self):
        self._setupTree1()
        if is_unix(): 
            self._test_exe2_path = path_join(self._tmpd, 'testf2')
            open(self._test_exe2_path, 'w').close()
            os.chmod(self._test_exe2_path, 744)
        elif is_windows():
            self._test_exe2_path = path_join(self._tmpd, 'testf2.exe')
            open(self._test_exe2_path, 'w').close()
        open(path_join(self._tmpd, 'f3test'), 'w').close()
        open(path_join(self._tmpd, 'otherfile'), 'w').close()
        os.mkdir(path_join(self._tmpd, 'testdir2'))
        open(path_join(self._tmpd, 'testdir2', 'blah'), 'w').close()
        open(path_join(self._tmpd, 'testdir2', 'moo'), 'w').close()
        os.mkdir(path_join(self._tmpd, 'testdir2', 'moodir'))    

    def testCmdOrShell(self):
        if is_windows():
            search='cmd'
        else:
            search='true'
            verbs = list(self.vc.completions(search, "."))
            self.assertNotEqual(len(verbs), 0)

    def testNoCompletion(self):
        if is_windows():
            search='cmd'
        else:
            search='true'
            verbs = list(self.vc.completions('this does not exist', "."))
            self.assertEquals(len(verbs), 0)

    def testCwd(self):
        self._setupTree1()
        results = list(self.pc.completions('testf', self._tmpd))
        self.assertEquals(len(results), 1)
        self.assertEquals(results[0].target.path, self._test_exe_path)

    def testCwd2(self):
        self._setupTree1()
        results = list(self.pc.completions('no such thing', self._tmpd))
        self.assertEquals(len(results), 0)

    def testCwd3(self):
        self._setupTree1()
        results = list(self.pc.completions('test', self._tmpd))
        self.assertEquals(len(results), 2)
        self.assertEquals(results[0].target.path, path_join(self._tmpd, 'testdir'))
        self.assertEquals(results[1].target.path, self._test_exe_path)

    def testCwd4(self):
        self._setupTree2()
        results = list(self.pc.completions('testdir2/', self._tmpd))
        self.assertEquals(len(results), 3)
        self.assertEquals(results[0].target.path, path_join(self._tmpd, 'testdir2', 'blah'))        
        self.assertEquals(results[0].suffix, 'blah')
        self.assertEquals(results[1].suffix, 'moo')
        self.assertEquals(results[2].suffix, 'moodir/')

    def testCwd5(self):
        self._setupTree2()
        results = list(self.pc.completions('testdir2/m', self._tmpd))
        self.assertEquals(len(results), 2)
        self.assertEquals(results[0].target.path, path_join(self._tmpd, 'testdir2', 'moo'))           
        self.assertEquals(results[0].suffix, 'oo')
        self.assertEquals(results[1].suffix, 'oodir/')
