"""Read-only audit of the clean public source selection; no secret files are read.

Generated build/cache/Git data is excluded, never deleted. Heuristic checks are
supplementary review evidence, not a credential or licensing certification.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tomllib
from urllib.parse import unquote, urlsplit

WRAPPER_PATH = 'android/gradle/wrapper/gradle-wrapper.jar'
# Gradle 8.13, verified at https://gradle.org/release-checksums/.
WRAPPER_SHA256 = '81a82aaea5abcc8ff68b3dfcb58b3c3c429378efd98e7433460610fecd7ae45f'
GRADLE_DISTRIBUTION_SHA256 = '20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78'
EXCLUDED_DIRS = {'.git', '.gradle', '.kotlin', '.idea', '.venv', 'venv', '__pycache__', 'build',
                 'dist', 'cache', 'caches', 'node_modules', '.pytest_cache', '.mypy_cache'}
EXCLUDED_FILES = {'local.properties', '.DS_Store', 'Thumbs.db'}
FORBIDDEN_SUFFIXES = {'.apk', '.aab', '.aar', '.dex', '.vdex', '.odex', '.oat', '.img', '.elf',
                      '.so', '.dll', '.exe', '.bin', '.db', '.sqlite', '.sqlite3', '.dump', '.hprof'}
SECRET_SUFFIXES = {'.pem', '.key', '.jks', '.keystore', '.p12', '.pfx', '.crt'}
TEXT_SUFFIXES = {'.py', '.kt', '.kts', '.java', '.xml', '.md', '.json', '.jsonl', '.toml',
                 '.yaml', '.yml', '.properties', '.txt', '.tsv', '.csv', '.bat', '.sh', '.typed'}
LOCAL_PACKAGES = {'monsieur_cuisine_sdk', 'mcc_protocol', 'mcs_protocol', 'mcc_powerboard_simulator',
                  'mcs_digital_twin', 'mcc_tools', 'mcs_tools'}
SOURCE_DIRECTORIES = {'.github', 'android', 'assets', 'docs', 'examples', 'fixtures',
                      'specs', 'src', 'tests', 'tools'}
SOURCE_ROOT_FILES = {'.gitignore', '.gitattributes', '.editorconfig', 'pyproject.toml',
                     'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md',
                     'CONTRIBUTING.md', 'SECURITY.md', 'RELEASE_NOTES.md', 'RELEASE_AUDIT.md'}
SOURCE_EXTENSIONLESS = {'.github/CODEOWNERS', 'android/gradlew',
                        'android/gradle/wrapper/LICENSE', 'android/gradle/wrapper/NOTICE'}
REQUIRED_FILES = (
    'pyproject.toml', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'src/monsieur_cuisine_sdk/__init__.py', '.github/FUNDING.yml', '.github/workflows/ci.yml',
    '.github/PULL_REQUEST_TEMPLATE.md', '.github/ISSUE_TEMPLATE/bug_report.yml',
    '.github/ISSUE_TEMPLATE/feature_request.yml',
    'RELEASE_NOTES.md', 'RELEASE_AUDIT.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md',
    'android/README.md',
) + tuple('docs/'+name+'.md' for name in (
    'index', 'setup', 'api', 'android', 'digital-twin', 'architecture', 'cli', 'recording',
    'scenarios', 'tests', 'evidence', 'protocols', 'migration', 'safety', 'faq', 'glossary',
    'troubleshooting', 'roadmap', 'releasing', 'first-steps', 'compatibility', 'quick-commands',
))
PATTERNS = (
    ('private absolute path', re.compile(r'(?i)(?<![A-Za-z0-9])[a-z]:[\\/]')),
    ('private home path', re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')),
    ('private key marker', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b')),
    ('cloud access token', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bya29\.[A-Za-z0-9_-]{40,}')),
    ('assigned credential', re.compile(r'''(?im)\b(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*["']([A-Za-z0-9+/=_-]{20,})["']''')),
)


def _issue(issues, path, reason, **metadata):
    issues.append({'path': path, 'reason': reason, **metadata})


def source_files(root):
    """Return deterministic selected paths and selection issues without opening keys."""
    root = Path(root).resolve()
    files, excluded, issues = [], [], []
    for directory, directories, names in os.walk(root, followlinks=False):
        base = Path(directory)
        keep = []
        for name in sorted(directories):
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                _issue(issues, rel, 'links/junctions are not source inputs')
            elif name in EXCLUDED_DIRS or name.endswith('.egg-info'):
                excluded.append(rel + '/')
                if name == '.git' and base != root:
                    _issue(issues, rel, 'nested Git checkout is not part of this project')
            else:keep.append(name)
        directories[:] = keep
        for name in sorted(names):
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                _issue(issues, rel, 'links are not source inputs')
            elif name == '.git':
                # A root .git file is a linked-worktree pointer (Git metadata);
                # elsewhere it marks a nested checkout or submodule.
                if base == root:excluded.append(rel)
                else:_issue(issues, rel, 'nested Git checkout is not part of this project')
            elif name in EXCLUDED_FILES or path.suffix in {'.pyc', '.pyo'}:
                excluded.append(rel)
            elif path.suffix.lower() in SECRET_SUFFIXES or name == '.env' or name.startswith('.env.') or name.lower() in {'credentials', 'id_rsa', 'id_ed25519'}:
                _issue(issues, rel, 'credential/key-like file rejected without reading content')
            elif path.suffix.lower() in FORBIDDEN_SUFFIXES:
                _issue(issues, rel, 'generated or proprietary binary/database is not public source')
            elif path.suffix.lower() == '.jar' and rel != WRAPPER_PATH:
                _issue(issues, rel, 'only the pinned official Gradle wrapper JAR is allowed')
            elif path.stat().st_size > 16 * 1024 * 1024:
                _issue(issues, rel, 'source file exceeds 16 MiB audit bound')
            else:files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix()), excluded, issues


def _local_links(root, path, content, selected, issues):
    for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', content):
        target = match.group(1).strip()
        if target.startswith('<') and '>' in target:target = target[1:target.index('>')]
        else:target = target.split(' "', 1)[0].split(" '", 1)[0]
        if not target or target.startswith('#'):continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:continue
        destination = (path.parent / unquote(parsed.path)).resolve()
        try:rel = destination.relative_to(root).as_posix()
        except ValueError:
            _issue(issues, path.relative_to(root).as_posix(), 'local Markdown link escapes source root')
            continue
        if not destination.exists() or (destination.is_file() and rel not in selected):
            _issue(issues, path.relative_to(root).as_posix(), 'broken/non-source local Markdown link', target=target)


def audit(root, *, project_checks=True, runtime=False):
    root = Path(root).resolve()
    paths, excluded, issues = source_files(root)
    selected = {p.relative_to(root).as_posix() for p in paths}
    manifest, images = [], []
    for path in paths:
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        manifest.append({'path': rel, 'bytes': len(raw), 'sha256': sha})
        if rel == WRAPPER_PATH:
            if sha != WRAPPER_SHA256:_issue(issues, rel, 'official wrapper hash mismatch')
            continue
        if path.suffix.lower() == '.png':
            allowed = rel.startswith('assets/screenshots/') or (rel.startswith('docs/devices/') and
                ('/research/resources/' in rel or '/legacy-assets/screenshots/' in rel))
            if not allowed:_issue(issues, rel, 'PNG requires an approved screenshot/research resource location')
            if len(raw) < 24 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
                _issue(issues, rel, 'invalid PNG structure')
            else:
                width, height = struct.unpack('>II', raw[16:24])
                if not (0 < width <= 50000 and 0 < height <= 50000):_issue(issues, rel, 'invalid PNG dimensions')
                images.append({'path': rel, 'width': width, 'height': height, 'sha256': sha,
                               'provenance': 'pixel authenticity requires capture/reviewer evidence; not inferred by this scanner'})
            continue
        try:content = raw.decode('utf-8')
        except UnicodeDecodeError:
            _issue(issues, rel, 'unapproved binary file')
            continue
        if '\0' in content:
            _issue(issues, rel, 'NUL-containing file is not approved text source')
            continue
        for label, pattern in PATTERNS:
            if pattern.search(content):_issue(issues, rel, label)
        if path.suffix == '.py':
            try:tree = ast.parse(content, filename=rel)
            except SyntaxError:_issue(issues, rel, 'invalid Python syntax');continue
            if rel.startswith('src/'):
                for node in ast.walk(tree):
                    modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and not node.level else []
                    for module in modules:
                        name = (module or '').split('.')[0]
                        if name and name not in sys.stdlib_module_names and name not in LOCAL_PACKAGES:
                            _issue(issues, rel, 'non-standard-library runtime import', module=name)
        if path.suffix in ('.json', '.jsonl'):
            try:
                def invalid_constant(value):raise ValueError(value)
                rows = content.splitlines() if path.suffix == '.jsonl' else [content]
                for row in rows:
                    if row.strip():json.loads(row, parse_constant=invalid_constant)
            except (ValueError, TypeError):_issue(issues, rel, 'invalid/nonfinite JSON')
        if path.suffix == '.md':_local_links(root, path, content, selected, issues)
        if rel == 'android/gradle/wrapper/gradle-wrapper.properties':
            properties=dict(line.strip().split('=',1) for line in content.splitlines() if '=' in line and not line.lstrip().startswith('#'))
            if properties.get('distributionUrl') != 'https\\://services.gradle.org/distributions/gradle-8.13-bin.zip' or properties.get('distributionSha256Sum') != GRADLE_DISTRIBUTION_SHA256:
                _issue(issues,rel,'Gradle distribution URL/checksum differs from pinned official 8.13')
    if project_checks:
        # Publication selection is explicit: a new reports/logs/clone tree or
        # unknown file format cannot silently enter an otherwise clean archive.
        for name in sorted(selected):
            relative = Path(name)
            if len(relative.parts) == 1:
                allowed = name in SOURCE_ROOT_FILES
            else:
                allowed = (relative.parts[0] in SOURCE_DIRECTORIES and
                           (relative.suffix.lower() in TEXT_SUFFIXES | {'.png', '.jar'}
                            or name in SOURCE_EXTENSIONLESS))
            if not allowed:_issue(issues, name, 'path or format is outside the public source allowlist')
        for name in REQUIRED_FILES:
            if name not in selected:_issue(issues, name, 'required source release file missing')
            elif not (root/name).read_text('utf-8').strip():_issue(issues,name,'required source release file is empty')
        if '.github/FUNDING.yml' in selected:
            entries=[line.split(':',1)[1].strip().strip('\'"').casefold() for line in (root/'.github/FUNDING.yml').read_text('utf-8').splitlines()
                     if line.strip().startswith('ko_fi:')]
            if entries!=['blackstufflabs']:_issue(issues,'.github/FUNDING.yml','expected public Ko-fi funding account is missing')
        if 'pyproject.toml' in selected:
            try:
                metadata = tomllib.loads((root/'pyproject.toml').read_text('utf-8'))
                if metadata['project'].get('dependencies', []):_issue(issues, 'pyproject.toml', 'runtime dependencies must remain empty')
                if metadata['build-system']['build-backend'] != 'setuptools.build_meta':_issue(issues, 'pyproject.toml', 'unexpected build backend')
            except (ValueError, KeyError):_issue(issues, 'pyproject.toml', 'invalid package metadata')
    if runtime:
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(root/'src')
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        code = "import sys; import monsieur_cuisine_sdk; assert 'socket' not in sys.modules; assert 'tkinter' not in sys.modules; from monsieur_cuisine_sdk import DigitalTwin; [DigitalTwin(m,record=False).get_state() for m in ('mcc','mcs')]; print('offline imports passed')"
        completed = subprocess.run([sys.executable, '-c', code], cwd=root.parent, env=environment,
                                   capture_output=True, text=True, timeout=30)
        if completed.returncode:_issue(issues, 'src/', 'offline runtime import/construction check failed')
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'passed': not issues, 'files': len(manifest), 'bytes': sum(row['bytes'] for row in manifest),
            'source_sha256': digest, 'issues': issues, 'excluded': excluded, 'images': images,
            'manifest': manifest, 'scope': 'selected source; ignored artifacts excluded without deletion; heuristic content review'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--json', type=Path)
    arguments = parser.parse_args(argv)
    result = audit(arguments.root, runtime=arguments.runtime)
    if arguments.json:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'manifest'}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':raise SystemExit(main())
