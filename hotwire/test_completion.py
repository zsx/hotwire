# -*- tab-width: 4 -*-
import os, sys, unittest, tempfile, shutil, platform

import hotwire
from hotwire.completion import *

class CompletionTests(unittest.TestCase):
    def setUp(self):
        self._tmpd = None

    def tearDown(self):
        if self._tmpd:
            shutil.rmtree(self._tmpd)

    def _setupTree1(self):
        self._tmpd = tempfile.mkdtemp(prefix='hotwiretest')
        os.mkdir(os.path.join(self._tmpd, 'testdir'))
        open(os.path.join(self._tmpd, 'testf'), 'w').close()
        os.mkdir(os.path.join(self._tmpd, 'dir with spaces'))
        os.chmod(os.path.join(self._tmpd, 'testf'), 744)

    def _setupTree2(self):
        self._setupTree1()
        open(os.path.join(self._tmpd, 'testf2'), 'w').close()
        os.chmod(os.path.join(self._tmpd, 'testf2'), 744)
        open(os.path.join(self._tmpd, 'f3test'), 'w').close()
        open(os.path.join(self._tmpd, 'otherfile'), 'w').close()
        os.mkdir(os.path.join(self._tmpd, 'testdir2'))
        open(os.path.join(self._tmpd, 'testdir2', 'blah'), 'w').close()

    def testCmdOrShell(self):
        if platform.system() == 'Windows':
            search='cmd'
        else:
            search='true'
            verbs = list(VerbCompleter(".").search(search))
            self.assertNotEqual(len(verbs), 0)					

    def testNoCompletion(self):
        if platform.system() == 'Windows':
            search='cmd'
        else:
            search='true'
            verbs = list(VerbCompleter(".").search('this does not exist'))
            self.assertEquals(len(verbs), 0)

    def testCwd(self):
        self._setupTree1()
        cwd = CwdExecutableCompleter(self._tmpd)
        results = list(cwd.search('testf'))
        self.assertEquals(len(results), 1)
        (mstr, start, mlen) = results[0].get_matchdata()
        self.assertEquals(mstr, os.path.join(self._tmpd, 'testf'))
        self.assertEquals(results[0].exact, True)
        self.assertEquals(mlen, 5)
        self.assertEquals(start, len(self._tmpd)+1)

    def testCwd2(self):
        self._setupTree1()
        cwd = CwdExecutableCompleter(self._tmpd)
        results = list(cwd.search('no such thing'))
        self.assertEquals(len(results), 0)

    def testCwd3(self):
        self._setupTree1()
        cwd = CwdExecutableCompleter(self._tmpd)
        results = list(cwd.search('test'))
        self.assertEquals(len(results), 2)
        (mstr, start, mlen) = results[0].get_matchdata()
        self.assertEquals(mstr, os.path.join(self._tmpd, 'testdir'))
        self.assertEquals(results[0].exact, False)
        (mstr, start, mlen) = results[1].get_matchdata()
        self.assertEquals(mstr, os.path.join(self._tmpd, 'testf'))
        self.assertEquals(results[1].exact, False)
