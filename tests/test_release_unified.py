"""Source selection, audit rejection and deterministic packaging regressions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
if str(TOOLS) not in sys.path:sys.path.insert(0,str(TOOLS))
from audit_release import audit,source_files,WRAPPER_PATH,REQUIRED_FILES
from build_release import build_source,mandatory_requirements,verify_wheel


class ReleaseSourceTests(unittest.TestCase):
    def test_installed_wheel_check_counts_only_unconditional_requirements(self):
        # Optional extras are opt-in; a wheel with only extras has no runtime dependency.
        self.assertEqual(mandatory_requirements(None),[])
        self.assertEqual(mandatory_requirements(['pyserial>=3.5,<4; extra == "serial"',
                                                 'capstone>=5,<6; extra=="analysis"']),[])
        self.assertEqual(mandatory_requirements(['requests>=2','x; python_version < "3.12"','y; extra == "z"']),
                         ['requests>=2','x; python_version < "3.12"'])

    def test_current_public_source_audit(self):
        result=audit(ROOT)
        self.assertTrue(result['passed'],result['issues'])
        selected={row['path'] for row in result['manifest']}
        self.assertTrue(set(REQUIRED_FILES).issubset(selected))
        with tempfile.TemporaryDirectory() as directory:
            fixture=Path(directory)
            (fixture/'README.md').write_text('Intentionally incomplete source fixture\n')
            (fixture/'reports').mkdir()
            (fixture/'reports/local-run.md').write_text('Not a public source deliverable\n')
            (fixture/'docs').mkdir()
            (fixture/'docs/accidental.log').write_text('Unreviewed log format\n')
            rejected=audit(fixture)
            missing={row['path'] for row in rejected['issues'] if row['reason']=='required source release file missing'}
            self.assertIn('.github/FUNDING.yml',missing)
            self.assertIn('.github/PULL_REQUEST_TEMPLATE.md',missing)
            self.assertIn('.github/ISSUE_TEMPLATE/bug_report.yml',missing)
            self.assertIn('.github/ISSUE_TEMPLATE/feature_request.yml',missing)
            self.assertIn('RELEASE_NOTES.md',missing)
            self.assertIn('docs/releasing.md',missing)
            self.assertIn('docs/first-steps.md',missing)
            self.assertIn('docs/compatibility.md',missing)
            self.assertIn('docs/quick-commands.md',missing)
            self.assertTrue(any(row['path']=='reports/local-run.md' and 'allowlist' in row['reason']
                                for row in rejected['issues']))
            self.assertTrue(any(row['path']=='docs/accidental.log' and 'allowlist' in row['reason']
                                for row in rejected['issues']))

    def test_keys_rejected_without_opening_their_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            key=root/'private.pem';key.write_text('not a real key',encoding='utf-8')
            original=Path.read_bytes
            def guarded(path):
                if path==key:raise AssertionError('key content was read')
                return original(path)
            with patch.object(Path,'read_bytes',guarded):result=audit(root,project_checks=False)
            self.assertFalse(result['passed'])
            self.assertIn('without reading',result['issues'][0]['reason'])

    def test_private_paths_tokens_invalid_json_and_broken_links_are_rejected(self):
        fixtures={
            'path.txt':'Q:'+chr(92)+'Users'+chr(92)+'someone'+chr(92)+'file',
            'token.txt':'gh'+'p_'+'A'*36,
            'bad.json':'{"temperature":NaN}',
            'broken.md':'[missing](absent.md)',
        }
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,text in fixtures.items():(root/name).write_text(text,encoding='utf-8')
            result=audit(root,project_checks=False)
            self.assertEqual({row['path'] for row in result['issues']},set(fixtures))
            rendered=json.dumps(result['issues'])
            self.assertNotIn('A'*36,rendered)

    def test_build_and_git_metadata_are_excluded_without_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ('.git','android/demo/build','android/.kotlin','cache'):
                path=root/folder;path.mkdir(parents=True)
                (path/'ignored.txt').write_text('ignored')
            (root/'README.md').write_text('source')
            result=audit(root,project_checks=False)
            self.assertTrue(result['passed'],result['issues'])
            self.assertEqual([row['path'] for row in result['manifest']],['README.md'])
            self.assertTrue((root/'android/demo/build/ignored.txt').exists())

    def test_nested_git_binary_and_unpinned_wrapper_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'clone/.git').mkdir(parents=True)
            (root/'firmware.bin').write_bytes(b'example')
            wrapper=root/WRAPPER_PATH;wrapper.parent.mkdir(parents=True)
            wrapper.write_bytes(b'not official wrapper')
            result=audit(root,project_checks=False)
            reasons=' '.join(row['reason'] for row in result['issues'])
            self.assertIn('nested Git',reasons)
            self.assertIn('binary/database',reasons)
            self.assertIn('hash mismatch',reasons)

    def test_nonstdlib_runtime_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src/demo').mkdir(parents=True)
            (root/'src/demo/__init__.py').write_text('import imaginary_third_party_library\n')
            result=audit(root,project_checks=False)
            self.assertTrue(any(row['reason']=='non-standard-library runtime import' for row in result['issues']))

    def test_source_archive_reproducible_metadata_manifest_and_no_generated_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'project';root.mkdir()
            for name in REQUIRED_FILES:
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text('Original test source\n')
            (root/'.github/FUNDING.yml').write_text('ko_fi: blackstufflabs\n')
            (root/'src/monsieur_cuisine_sdk').mkdir(parents=True,exist_ok=True)
            (root/'src/monsieur_cuisine_sdk/__init__.py').write_text('"""Test fixture."""\n')
            (root/'pyproject.toml').write_text('[build-system]\nrequires=["setuptools>=77"]\nbuild-backend="setuptools.build_meta"\n[project]\nname="test"\nversion="0.1.0"\ndependencies=[]\n')
            generated=root/'android/demo/build/outputs/apk/debug';generated.mkdir(parents=True)
            (generated/'demo-debug.apk').write_bytes(b'not exported into source')
            a=build_source(root,Path(directory)/'first')
            b=build_source(root,Path(directory)/'second')
            self.assertEqual(Path(a['archive']).read_bytes(),Path(b['archive']).read_bytes())
            self.assertEqual(Path(a['source_manifest']).read_bytes(),Path(b['source_manifest']).read_bytes())
            with zipfile.ZipFile(a['archive']) as source:
                for item in source.infolist():
                    self.assertEqual(item.date_time,(1980,1,1,0,0,0))
                    self.assertNotIn('/build/',item.filename)
                    self.assertFalse(item.filename.endswith('.apk'))
                for row in a['files']:
                    self.assertEqual(hashlib.sha256(source.read(a['name']+'/'+row['path'])).hexdigest(),row['sha256'])
            self.assertTrue((generated/'demo-debug.apk').exists())
            with self.assertRaises(ValueError):build_source(root,root/'dist')
            # A local OS policy rejection must never become a console PASS.
            # Exercise its explicit module alternative without creating a venv.
            def policy_runner(arguments,**kwargs):
                if Path(arguments[0]).name in ('mc-sdk','mc-sdk.exe'):
                    error=OSError('simulated Windows application control rejection')
                    error.winerror=4551
                    raise error
                return subprocess.CompletedProcess(arguments,0,'','')
            with patch('build_release.venv.EnvBuilder'),patch('build_release.subprocess.run',side_effect=policy_runner):
                with self.assertRaisesRegex(ValueError,'Windows policy'):
                    verify_wheel(root,Path(directory)/'first',Path(directory)/'fixture.whl')
                blocked=verify_wheel(root,Path(directory)/'first',Path(directory)/'fixture.whl',
                                     gui=True,record_windows_launcher_block=True)
            self.assertFalse(blocked['passed'])
            self.assertFalse(blocked['console_launcher_verified'])
            self.assertTrue(blocked['windows_launcher_policy_blocked'])
            self.assertTrue(blocked['functional_checks_passed'])
            self.assertTrue(blocked['gui_executed'])
            self.assertEqual(sum(row['status']=='blocked_by_windows_appcontrol' for row in blocked['checks']),1)
            self.assertEqual(sum(row['status']=='not_run_after_windows_policy_block' for row in blocked['checks']),3)
            module_checks=[row for row in blocked['checks'] if 'monsieur_cuisine_sdk.cli' in row['command']]
            self.assertEqual(len(module_checks),4)
            self.assertTrue(all(row['status']=='passed' for row in module_checks))


if __name__=='__main__':unittest.main()
