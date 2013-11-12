# Copyright 2013, Red Hat Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from distutils import dir_util
import logging
import os
import shutil
import subprocess
import sys

from diskimage_builder import element
from diskimage_builder import element_dependencies


class ElementRunner(object):

    def __init__(self, elements, hooks, element_paths=None, blacklist=None,
                 exclude_elements=None, dry_run=False, interactive=False):
        """Element Runner initialization.

        :param elements: Element names to apply.
        :type elements: list.
        :param hooks: Hooks to run for each element.
        :type hooks: list.
        :param element_paths: File system paths to search for elements.
        :type element_paths: list of strings.
        :param blacklist: Script names to blacklist and not execute.
        :type blacklist: list.
        :param exclude_elements: Element names to exclude and not apply.
        :type exclude_elements: list.
        :param dry_run: If True, do not actually run the hooks.
        :type dry_run: bool
        """
        self.elements = elements
        self.dry_run = dry_run
        self.hooks = hooks
        self.blacklist = blacklist or []
        self.exclude_elements = exclude_elements or []
        self.interactive = interactive
        self.loaded_elements = {}
        self.tmp_hook_dir = '/tmp/in_target.d'

        # the environment variable should override anything passed in
        if 'ELEMENTS_PATH' in os.environ:
            self.element_paths = os.environ['ELEMENTS_PATH'].split(':')
        else:
            self.element_paths = element_paths

        if self.element_paths is None:
            raise Exception("No element paths specified")

        logging.info('manager initialized with elements path: %s' %
                     self.element_paths)

    def run(self):
        """Apply the elements by running each specified hook."""

        self.load_elements()
        self.load_dependencies()
        self.process_exclude_elements()
        self.copy_elements()

        for hook in self.hooks:
            logging.info("running hook: %s" % hook)
            self.run_hook(hook)

        self.cleanup()

    def cleanup(self):
        """Clean up after a run."""
        shutil.rmtree(self.tmp_hook_dir)

    def load_elements(self):
        """Load all elements from self.element_paths.

        This populates self.loaded_elements.
        """
        for path in self.element_paths:
            self.process_path(path)

    def copy_elements(self):
        """Copy elements to apply to a temporary directory."""
        # self.tmp_hook_dir may exist from a previous run, delete it if so.
        if os.path.exists(self.tmp_hook_dir):
            shutil.rmtree(self.tmp_hook_dir)

        os.makedirs(self.tmp_hook_dir)

        for elem in self.elements:
            element_dir = self.loaded_elements[elem].directory
            dir_util.copy_tree(element_dir, self.tmp_hook_dir)

        # elements expect this environment variable to be set
        os.environ['TMP_HOOKS_PATH'] = self.tmp_hook_dir
        tmp_path = '%s/bin' % self.tmp_hook_dir
        if 'PATH' in os.environ:
            tmp_path = os.environ["PATH"] + os.pathsep + tmp_path
        os.environ["PATH"] = tmp_path

    def process_path(self, path):
        """Load elements from a given filesystem path.

        :param path: Filesystem path from which to load elements.
        :type path: str.
        """
        if not os.access(path, os.R_OK):
            raise Exception("Can't read from elements path at %s." % path)

        for elem in os.listdir(path):
            if not os.path.isdir(os.path.join(path, elem)):
                continue
            if elem in self.loaded_elements:
                raise Exception("Element %s already loaded." % elem)
            self.loaded_elements[elem] = element.Element(
                os.path.join(path, elem))

    def load_dependencies(self):
        """Load and add all element dependencies to self.elements."""
        all_elements = element_dependencies.expand_dependencies(
            self.elements, ':'.join(self.element_paths))
        self.elements = all_elements

    def process_exclude_elements(self):
        """Remove any elements that have been specified as excluded."""
        for elem in self.exclude_elements:
            if elem in self.elements:
                logging.info("Excluding element %s" % elem)
                self.elements.remove(elem)

    def run_hook(self, hook):
        """Run a hook on the current system.

        :param hook: name of hook to run
        :type hook: str
        """
        hook_dir = os.path.join(self.tmp_hook_dir, '%s.d' % hook)
        if not os.path.exists(hook_dir):
            logging.info("Skipping hook %s, the hook directory doesn't "
                         "exist at %s" % (hook, hook_dir))
            return

        # Need to figure out the full path to dib-run-parts first b/c later
        # when we call it via sudo, $PATH is not preserved.
        rc, stdout = call(['which', 'dib-run-parts'])
        dib_run_parts_path = stdout.strip('\n')

        if not self.dry_run:
            rc, stdout = call(['/bin/sudo', '-E',
                               dib_run_parts_path, hook_dir])
        else:
            logging.info("Dry run specified, would have executed: %s" %
                         ['/bin/sudo', '-E', dib_run_parts_path, hook_dir])

        if rc != 0:
            logging.error("dib-run-parts hook failed: %s" % hook_dir)
            if self.interactive:
                logging.error("Continue? (y/n): ")
                sys.stdout.flush()
                entry = raw_input("")
                if entry.lower() == 'y':
                    logging.info("continuing on user command.")
                    return

            logging.error("exiting after failure.")
            sys.exit(rc)


def call(*args, **kwargs):
    """Call out to run a command via subprocess."""

    logging.info('executing command: %s' % args)
    # all output to stdout/stderr for now.
    p = subprocess.Popen(*args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         env=os.environ,
                         **kwargs)

    rc = p.wait()
    stdout = p.stdout.read()
    print(stdout)
    logging.info('exited with code: %s' % rc)
    return rc, stdout
