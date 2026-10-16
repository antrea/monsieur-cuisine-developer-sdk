"""Run each native GUI case in a fresh process, like the desktop entry point.

Tk's native application lifetime is process-wide on some platforms. Repeatedly
destroying and recreating its interpreter in an otherwise shared test process
does not represent normal application use. Every assertion still runs against
real widgets; a child crash, timeout or failed assertion fails the parent case.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class NativeGuiTestCase(unittest.TestCase):
    def run(self, result=None):
        if os.environ.get("MC_SDK_GUI_TEST_CASE") == self.id():
            return super().run(result)
        if result is None:
            result = self.defaultTestResult()
        result.startTest(self)
        environment = dict(os.environ)
        environment["MC_SDK_GUI_TEST_CASE"] = self.id()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parent), *sys.path]
        )
        try:
            child = subprocess.run(
                [sys.executable, "-X", "faulthandler", "-m", "unittest", self.id(), "-v"],
                env=environment, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        except self.failureException:
            result.addFailure(self, sys.exc_info())
        except Exception:
            result.addError(self, sys.exc_info())
        else:
            result.addSuccess(self)
        finally:
            result.stopTest(self)
        return result
