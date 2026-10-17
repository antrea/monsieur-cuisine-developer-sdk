"""Release selection must match a clean commit when the root is a Git top level."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:sys.path.insert(0, str(TOOLS))
from audit_release import audit, REQUIRED_FILES
from build_release import build_source


def fixture(root):
    for name in REQUIRED_FILES:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('Original test source\n')
    (root / '.github/FUNDING.yml').write_text('ko_fi: blackstufflabs\n')
    (root / 'src/monsieur_cuisine_sdk/__init__.py').write_text('"""Test fixture."""\n')
    (root / 'pyproject.toml').write_text('[build-system]\nrequires=["setuptools>=77"]\nbuild-backend="setuptools.build_meta"\n'
                                         '[project]\nname="test"\nversion="0.1.0"\ndependencies=[]\n')


class ReleaseGitSelection(unittest.TestCase):
    def test_root_worktree_pointer_file_is_metadata_not_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.git').write_text('gitdir: ../elsewhere/.git/worktrees/x\n')
            (root / 'README.md').write_text('source')
            result = audit(root, project_checks=False)
            self.assertTrue(result['passed'], result['issues'])
            self.assertIn('.git', result['excluded'])
            (root / 'docs').mkdir(); (root / 'docs/.git').write_text('gitdir: nested\n')
            self.assertIn('nested Git', ' '.join(row['reason'] for row in audit(root, project_checks=False)['issues']))

    @unittest.skipIf(shutil.which('git') is None, 'git is required for this release check')
    def test_untracked_and_uncommitted_files_cannot_enter_the_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'; root.mkdir()
            fixture(root)
            git = ['git', '-C', str(root), '-c', 'user.name=release-test', '-c', 'user.email=release@example.invalid',
                   '-c', 'core.autocrlf=false', '-c', 'commit.gpgsign=false']
            subprocess.run([*git, 'init', '-q'], check=True)
            subprocess.run([*git, 'add', '-A'], check=True)
            subprocess.run([*git, 'commit', '-q', '-m', 'fixture'], check=True)
            build_source(root, Path(directory) / 'clean')
            (root / 'docs/private-notes.md').write_text('local notes\n')
            with self.assertRaisesRegex(ValueError, 'untracked file'):
                build_source(root, Path(directory) / 'untracked')
            (root / 'docs/private-notes.md').unlink()
            (root / 'README.md').write_text('edited after the commit\n')
            with self.assertRaisesRegex(ValueError, 'uncommitted change'):
                build_source(root, Path(directory) / 'modified')


if __name__ == '__main__':
    unittest.main()
