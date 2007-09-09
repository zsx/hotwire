# -*- tab-width: 4 -*-
import os, sys, unittest, tempfile, shutil

import hotwire
from hotwire.command import *
from hotwire.fs import unix_basename

class PipelineParserTests(unittest.TestCase):
    def setUp(self):
        self._context = HotwireContext()

    def tearDown(self):
        self._context = None
    
    def testEmacs(self):
        pt = Pipeline.parse_tree('emacs', self._context, assertfn=self.assertEquals)
        self.assertEquals(len(pt), 1)
        self.assertEquals(len(pt[0]), 1)
        self.assertEquals(pt[0][0].text, 'emacs')

    def testEmacsFile(self):
        pt = Pipeline.parse_tree('emacs /tmp/foo.txt', self._context, assertfn=self.assertEquals)
        self.assertEquals(len(pt), 1)
        self.assertEquals(len(pt[0]), 2)
        self.assertEquals(pt[0][0].text, 'emacs')
        self.assertEquals(pt[0][1].text, '/tmp/foo.txt')

    def testEmacsFileSpace(self):
        pt = Pipeline.parse_tree("emacs 'foo bar'", self._context, assertfn=self.assertEquals)
        self.assertEquals(len(pt), 1)
        self.assertEquals(len(pt[0]), 2)
        self.assertEquals(pt[0][0].text, 'emacs')
        self.assertEquals(pt[0][1].text, "foo bar")

    def testEmacsFileSpaces(self):
        pt = Pipeline.parse_tree("emacs 'foo bar' baz 'whee cow crack'", self._context, assertfn=self.assertEquals)
        self.assertEquals(len(pt), 1)
        self.assertEquals(len(pt[0]), 4)
        self.assertEquals(pt[0][0].text, 'emacs')
        self.assertEquals(pt[0][1].text, "foo bar")
        self.assertEquals(pt[0][2].text, "baz")
        self.assertEquals(pt[0][3].text, "whee cow crack")

    def testLsMulti(self):
        pt = Pipeline.parse_tree('ls foo.py bar.py baz.py', self._context, assertfn=self.assertEquals)
        self.assertEquals(len(pt), 1)

    def testMulti(self):
        pt = Pipeline.parse_tree('sh echo true | sh cat /tmp/foo.txt', self._context)
        self.assertEquals(len(pt), 2)

    def testMulti4(self):
        pt = Pipeline.parse_tree('sh echo true | sh cat /tmp/foo.txt | sh echo moo  cow | sh cat cat cat /tmp/foo.txt', self._context)
        self.assertEquals(len(pt), 4)

    def testPathological1(self):
        pt = Pipeline.parse_tree('cat | ls', self._context)
        self.assertEquals(len(pt), 2)

class PipelineInstantiateTests(unittest.TestCase):
    def setUp(self):
        self._context = HotwireContext()

    def tearDown(self):
        self._context = None

    def testSh(self):
        p = Pipeline.parse('sh echo true', self._context)
        self.assertEquals(p.get_input_type(), str)
        self.assertEquals(p.get_output_type(), str)
        self.assertEquals(p.get_undoable(), False)
        self.assertEquals(p.get_idempotent(), False)

    def testShFilter(self):
        p = Pipeline.parse('sh echo true | filter true', self._context)
        self.assertEquals(p.get_input_type(), str)
        self.assertEquals(p.get_output_type(), str)
        self.assertEquals(p.get_undoable(), False)
        self.assertEquals(p.get_idempotent(), False)

    def testPs(self):
        p = Pipeline.parse('proc', self._context)
        self.assertEquals(p.get_input_type(), None)
        self.assertEquals(p.get_output_type(), hotwire.sysdep.proc.Process)
        self.assertEquals(p.get_undoable(), False)
        self.assertEquals(p.get_idempotent(), True)

    def testMv(self):
        p = Pipeline.parse('mv foo bar', self._context)
        self.assertEquals(p.get_input_type(), None)
        self.assertEquals(p.get_output_type(), None)
        self.assertEquals(p.get_undoable(), False)
        self.assertEquals(p.get_idempotent(), False)

    def testRm(self):
        p = Pipeline.parse('rm foo bar', self._context)
        self.assertEquals(p.get_input_type(), None)
        self.assertEquals(p.get_output_type(), None)
        self.assertEquals(p.get_undoable(), True)
        self.assertEquals(p.get_idempotent(), False)

    def testInvalid1(self):
        self.assertRaises(hotwire.command.PipelineParseException, lambda: Pipeline.parse('mv foo bar | sh cat', self._context))

    def testInvalid2(self):
        self.assertRaises(hotwire.command.PipelineParseException, lambda: Pipeline.parse('sh cat | proc', self._context))

    def testInvalid3(self):
        self.assertRaises(hotwire.command.PipelineParseException, lambda: Pipeline.parse('filter foo', self._context))

    def testInvalid4(self):
        self.assertRaises(hotwire.command.PipelineParseException, lambda: Pipeline.parse('ls | cd test', self._context))

class PipelineRunTestFramework(unittest.TestCase):
    def setUp(self):
        self._context = HotwireContext()
        self._tmpd = tempfile.mkdtemp(prefix='hotwiretest')
        self._context.chdir(self._tmpd)

    def tearDown(self):
        self._context = None
        shutil.rmtree(self._tmpd)

    def _setupTree1(self):
        os.mkdir(os.path.join(self._tmpd, 'testdir'))
        open(os.path.join(self._tmpd, 'testf'), 'w').close()
        os.mkdir(os.path.join(self._tmpd, 'dir with spaces'))

    def _setupTree2(self):
        self._setupTree1()
        open(os.path.join(self._tmpd, 'testf2'), 'w').close()
        open(os.path.join(self._tmpd, 'f3test'), 'w').close()
        open(os.path.join(self._tmpd, 'otherfile'), 'w').close()
        os.mkdir(os.path.join(self._tmpd, 'testdir2'))
        open(os.path.join(self._tmpd, 'testdir2', 'blah'), 'w').close()


class PipelineRunTests(PipelineRunTestFramework):
    def testPs(self):
        p = Pipeline.parse('proc', self._context)
        p.execute_sync()

    def testPsFilter(self):
        p = Pipeline.parse('proc | filter python cmd', self._context)
        p.execute()
        found_objs = False
        for obj in p.get_output(): 
            found_objs = True
            break
        self.assert_(found_objs)

    def testPsFilter2(self):
        p = Pipeline.parse('proc | filter this-command-does-not-exist cmd', self._context)
        p.execute()
        found_objs = False
        for obj in p.get_output(): 
            found_objs = True
            break
        self.assert_(not found_objs)

    def testRm(self):
        self._setupTree1()
        testf_path = os.path.join(self._tmpd, 'testf') 
        self.assertEquals(os.access(testf_path, os.R_OK), True)
        p = Pipeline.parse('rm testf', self._context)
        p.execute_sync()
        self.assertEquals(os.access(testf_path, os.R_OK), False)

    def testRm2(self):
        self._setupTree1()
        testf_path = os.path.join(self._tmpd, 'testf') 
        self.assertEquals(os.access(testf_path, os.R_OK), True)
        p = Pipeline.parse('rm %s' % (testf_path,), self._context)
        p.execute_sync()
        self.assertEquals(os.access(testf_path, os.R_OK), False)

    def testRm3(self):
        self._setupTree2()
        p = Pipeline.parse('rm test* f3test', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf2'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'f3test'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), True)

    def testRm4(self):
        self._setupTree2()
        p = Pipeline.parse('rm %s %s' % (os.path.join(self._tmpd, 'f3test'), os.path.join(self._tmpd, 'otherfile')),
                           self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), True)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'f3test'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), False)

    def testRm5(self):
        self._setupTree1()
        p = Pipeline.parse('rm testf', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), False)
        open(os.path.join(self._tmpd, 'testf'), 'w').close()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), True)
        p = Pipeline.parse('rm testf', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), False)

    def testRm6(self):
        self._setupTree1()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), True)
        p = Pipeline.parse("rm 'dir with spaces'", self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), False)

    def testRm7(self):
        self._setupTree1()
        testf_path = os.path.join(self._tmpd, 'testf') 
        self.assertEquals(os.access(testf_path, os.R_OK), True)
        p = Pipeline.parse('rm testf', self._context)
        p.execute_sync()
        self.assertEquals(os.access(testf_path, os.R_OK), False)
        p.undo()
        self.assertEquals(os.access(testf_path, os.R_OK), True)

    def testMv(self):
        self._setupTree2()
        p = Pipeline.parse('mv testf testdir', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir', 'testf'), os.R_OK), True)

    def testMv2(self):
        self._setupTree2()
        p = Pipeline.parse('mv testf testdir', self._context)
        p.execute_sync()
        p = Pipeline.parse('mv testdir testdir2', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir'), os.R_OK), False)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir2', 'testdir', 'testf'), os.R_OK), True)

    def testCd(self):
        self._setupTree1()
        oldwd = self._context.get_cwd()
        p = Pipeline.parse('cd testdir', self._context)
        p.execute_sync()
        self.assertEquals(self._context.get_cwd(), os.path.abspath(os.path.join(oldwd, 'testdir')))

    def testLs(self):
        self._setupTree1()
        p = Pipeline.parse("ls *test*", self._context)
        p.execute_sync()
        results = list(p.get_output())
        results.sort()
        self.assertEquals(len(results), 2)
        self.assertEquals(os.path.dirname(results[0]), self._tmpd)
        self.assertEquals(unix_basename(results[0]), 'testdir')
        self.assertEquals(os.path.dirname(results[1]), self._tmpd)
        self.assertEquals(unix_basename(results[1]), 'testf')

    def testLs2(self):
        p = Pipeline.parse("ls ~", self._context)
        p.execute_sync()

    def testLs3(self):
        self._setupTree1()
        p = Pipeline.parse("ls testdir", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)

    def testLs4(self):
        self._setupTree1()
        p = Pipeline.parse("ls | filter spac", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 1)
        self.assertEquals(os.path.dirname(results[0]), self._tmpd)
        self.assertEquals(unix_basename(results[0]), 'dir with spaces')

    def testLs5(self):
        self._setupTree1()
        hidden = os.path.join(self._tmpd, '.nosee')
        open(hidden, 'w').close()
        p = Pipeline.parse("ls", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 3)

    def testLs6(self):
        self._setupTree1()
        hidden = os.path.join(self._tmpd, '.nosee')
        open(hidden, 'w').close()
        p = Pipeline.parse("ls -a", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 4)

    def testLsQuoted(self):
        self._setupTree1()
        hidden = os.path.join(self._tmpd, "foo'bar")
        open(hidden, 'w').close()
        p = Pipeline.parse("ls \"foo'bar\"", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 1)

    def testCdQuoted(self):
        self._setupTree1()
        p = os.path.join(self._tmpd, "foo'bar")
        os.mkdir(p)
        p = Pipeline.parse("cd \"foo'bar\"", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)

    def testCdQuoted2(self):
        self._setupTree1()
        p = os.path.join(self._tmpd, "foo\"bar")
        os.mkdir(p)
        p = Pipeline.parse("cd 'foo\"bar'", self._context)
        p.execute_sync()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)

    def testCp(self):
        self._setupTree2()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf3'), os.R_OK), False)
        p = Pipeline.parse('cp testf testf3', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), True)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf3'), os.R_OK), True)
        
    def testCp2(self):
        self._setupTree2()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir', 'testf'), os.R_OK), False)
        p = Pipeline.parse('cp testf testdir', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testf'), os.R_OK), True)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir', 'testf'), os.R_OK), True)

    def testCp3(self):
        self._setupTree2()
        p = Pipeline.parse('cp testf testdir2/blah', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir2', 'blah'), os.R_OK), True)

    def testCp4(self):
        self._setupTree2()
        p = Pipeline.parse('cp testdir2 testdir3', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir3', 'blah'), os.R_OK), True)

    def testCp5(self):
        self._setupTree2()
        p = Pipeline.parse('cp testf \'dir with spaces\' testdir2', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir2', 'testf'), os.R_OK), True)
        self.assertEquals(os.access(os.path.join(self._tmpd, 'testdir2', 'dir with spaces'), os.R_OK), True)

def suite():
    loader = unittest.TestLoader()
    loader.loadTestsFromTestCase(PipelineParserTests)
    
    suite.addTest(PipelineParserTests())
    suite.addTest(PipelineInstantiateTests())
    return suite
