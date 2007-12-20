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

import os,sys,time

import hotwire
from hotwire.command import *
from hotwire.test_command import PipelineRunTestFramework
from hotwire.fs import unix_basename

class PipelineRunTestsUnix(PipelineRunTestFramework):
    def testSh(self):
        self._setupTree1()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), False)
        p = Pipeline.parse('sys touch otherfile', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'otherfile'), os.R_OK), True)

    def testSh2(self):
        self._setupTree1()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'file with spaces'), os.R_OK), False)
        p = Pipeline.parse('sys touch "file with spaces"', self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'file with spaces'), os.R_OK), True)

    def testSh3(self):
        self._setupTree2()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), True)
        p = Pipeline.parse("sys rmdir 'dir with spaces'", self._context)
        p.execute_sync()
        self.assertEquals(os.access(os.path.join(self._tmpd, 'dir with spaces'), os.R_OK), False)

    def testSh4(self):
        self._setupTree1()
        p = Pipeline.parse("sys ls -1 -d *test*", self._context)
        p.execute_sync()
        results = list(p.get_output())
        results.sort()
        self.assertEquals(len(results), 2)
        self.assertEquals(results[0], 'testdir')
        self.assertEquals(results[1], 'testf')

    def testSh5(self):
        self._setupTree1()
        p = Pipeline.parse("sys ls -1 -d *test* | filter dir", self._context)
        p.execute_sync()
        results = list(p.get_output())
        results.sort()
        self.assertEquals(len(results), 1)
        self.assertEquals(results[0], 'testdir')            

    def testShCancel1(self):
        p = Pipeline.parse("sys sleep 30", self._context)
        p.execute()
        p.cancel()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)

    def testShCancel2(self):
        p = Pipeline.parse("sys sleep 15", self._context)
        p.execute()
        time.sleep(2)
        p.cancel()
        results = list(p.get_output())
        self.assertEquals(len(results), 0)
