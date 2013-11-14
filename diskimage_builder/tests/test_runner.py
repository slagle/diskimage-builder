# Copyright 2013 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import mock
import os
import tempfile
import testtools

from diskimage_builder import runner


class TestRunner(testtools.TestCase):

    def setUp(self):
        super(TestRunner, self).setUp()
        cwd = os.path.dirname(__file__)
        dib_elements = os.path.join(cwd, '..', '..', 'elements')
        test_elements = os.path.join(cwd, 'elements')
        self.element_paths = [dib_elements, test_elements]

        self.runner = runner.ElementRunner(['dep2', 'echo'], [],
                                           self.element_paths)
        tmp_dir = tempfile.mkdtemp()
        self.runner.tmp_hook_dir = tmp_dir

    def test_cleanup(self):
        self.runner.cleanup()
        self.assertFalse(os.path.exists(self.runner.tmp_hook_dir))

    @mock.patch.object(runner.ElementRunner, 'process_path')
    def test_load_elements(self, mock_method):
        self.runner.load_elements()

        self.assertEqual(len(self.element_paths), mock_method.call_count)
        for idx in range(len(self.element_paths)):
            self.assertEqual(mock.call(self.element_paths[idx]),
                             mock_method.call_args_list[idx])

    def test_copy_elements(self):
        self.runner.load_elements()
        self.runner.copy_elements()

        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.runner.tmp_hook_dir, 'install.d', '50-echo')))
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.runner.tmp_hook_dir, 'install.d', '50-dep2')))

    def test_load_dependencies(self):
        self.runner.load_elements()
        self.runner.copy_elements()
        self.runner.load_dependencies()

        self.assertEqual(len(self.runner.elements), 3)
        self.assertTrue('dep1' in self.runner.elements)

    def test_process_exclude_elements(self):
        self.runner.exclude_elements = ['dep1']

        self.runner.load_elements()
        self.runner.copy_elements()
        self.runner.load_dependencies()
        self.runner.process_exclude_elements()

        self.assertEqual(len(self.runner.elements), 2)
        self.assertFalse('dep1' in self.runner.elements)

    def test_process_path(self):
        cwd = os.path.dirname(__file__)
        test_elements = os.path.join(cwd, 'elements')
        self.runner.process_path(test_elements)

        self.assertEqual(len(self.runner.loaded_elements), 6)
        self.assertTrue('dep1' in self.runner.loaded_elements)
        self.assertTrue('dep2' in self.runner.loaded_elements)
        self.assertTrue('echo' in self.runner.loaded_elements)
        self.assertTrue('error' in self.runner.loaded_elements)
        self.assertTrue('output' in self.runner.loaded_elements)
        self.assertTrue('repo' in self.runner.loaded_elements)

        self.assertRaises(Exception, self.runner.process_path,
                          '/tmp/non/existant/path')

    @mock.patch('diskimage_builder.runner.call',
                return_value=(0, '/path/to/dib-run-parts'))
    def test_run_hook(self, mock_call):
        self.runner.load_elements()
        self.runner.copy_elements()
        self.runner.load_dependencies()
        self.runner.process_exclude_elements()

        self.runner.run_hook('install')

        self.assertEqual(mock_call.call_count, 2)
        self.assertEqual(
            mock.call(['which', 'dib-run-parts']),
            mock_call.call_args_list[0])
        self.assertEqual(
            mock.call(['/bin/sudo', '-E', '/path/to/dib-run-parts',
                      os.path.join(self.runner.tmp_hook_dir, 'install.d')]),
            mock_call.call_args_list[1])
