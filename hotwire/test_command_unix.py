import os,sys,time

import hotwire
from hotwire.command import *
from hotwire.test_command import PipelineRunTestFramework
from hotwire.fs import unix_basename

class PipelineRunTestsUnix(PipelineRunTestFramework):
    def testSh(self):
        self._setupTree1()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), False)
        p = Pipeline.parse('sh touch otherfile', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), True)

    def testSh2(self):
        self._setupTree1()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'file with spaces'), os.R_OK), False)
        p = Pipeline.parse('sh touch "file with spaces"', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'file with spaces'), os.R_OK), True)

    def testSh3(self):
        self._setupTree2()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), True)
        p = Pipeline.parse("sh rmdir 'dir with spaces'", self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), False)

    def testSh4(self):
        self._setupTree1()
        p = Pipeline.parse("sh ls -1 -d *test*", self._context)
        p.execute_sync()
        results = list(p.get_output())
        results.sort()
        self.assertEquals(len(results), 2)
        self.assertEquals(results[0], 'testdir')
        self.assertEquals(results[1], 'testf')

    def testSh5(self):
        self._setupTree1()
        p = Pipeline.parse("sh ls -1 -d *test* | filter dir", self._context)
        p.execute_sync()
        results = list(p.get_output())
        results.sort()
        self.assertEquals(len(results), 1)
        self.assertEquals(results[0], 'testdir')

    def testShCancel1(self):
        p = Pipeline.parse("sh sleep 30", self._context)
        p.execute()
        p.cancel()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)

    def testShCancel2(self):
        p = Pipeline.parse("sh sleep 15", self._context)
        p.execute()
        time.sleep(2)
        p.cancel()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)
