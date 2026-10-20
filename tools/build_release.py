"""Deterministic source ZIP and optional separately built artifacts, outside checkout.

Use optional wheel/binary arguments only after the release owner freezes code and
tests. Never publishes, signs, changes Git state, or deletes build directories.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import tempfile
import venv
import zipfile

from audit_release import audit


def mandatory_requirements(requires):
    """Requirements without an ``extra ==`` marker: what every installation pulls in.

    ``importlib.metadata.requires`` also lists optional extras such as
    ``pyserial>=3.5,<4; extra == "serial"``. Those are opt-in and do not make the
    wheel depend on third-party code; other markers (Python version, platform)
    still count as mandatory.
    """
    import re
    mandatory = []
    for requirement in requires or ():
        _name, _separator, marker = requirement.partition(';')
        if not re.search(r'\bextra\s*==', marker):
            mandatory.append(requirement.strip())
    return mandatory


def git_selection_issues(root, selected):
    """Selected files that are untracked or uncommitted when root is a Git top level.

    The audit walks the filesystem; without this check a private untracked file
    in an allowlisted directory (for example docs/notes.md) would be archived.
    Archives that are not their own Git top level are left to the audit alone.
    """
    try:
        top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=30)
    except OSError:
        return []
    if top.returncode or Path(top.stdout.strip()).resolve() != Path(root).resolve():
        return []
    def git(*arguments):
        done = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, timeout=60, check=True)
        return [entry for entry in done.stdout.decode('utf-8').split('\0') if entry]
    tracked = set(git('ls-files', '-z'))
    changed = {entry[3:] for entry in git('status', '--porcelain=v1', '-z', '--untracked-files=all')
               if len(entry) > 3 and entry[:2] != '??'}
    issues = []
    for path in sorted(selected):
        if path not in tracked:issues.append({'path': path, 'reason': 'untracked file would enter the release'})
        elif path in changed:issues.append({'path': path, 'reason': 'uncommitted change would enter the release'})
    return issues


def build_source(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or output.is_relative_to(root):raise ValueError('release output must be outside the public checkout')
    checked = audit(root)
    if not checked['passed']:raise ValueError('source audit failed: ' + json.dumps(checked['issues']))
    selection = git_selection_issues(root, {row['path'] for row in checked['manifest']})
    if selection:raise ValueError('release selection is not a clean commit: ' + json.dumps(selection[:20]))
    version = tomllib.loads((root/'pyproject.toml').read_text('utf-8'))['project']['version']
    if not isinstance(version,str) or not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+-]*',version):raise ValueError('invalid release version')
    name = f'monsieur-cuisine-developer-sdk-{version}'
    output.mkdir(parents=True, exist_ok=True)
    archive = output/f'{name}-source.zip'
    manifest = {'format': 'source-manifest-v1', 'name': name, 'source_sha256': checked['source_sha256'], 'files': checked['manifest']}
    manifest_path = output/f'{name}-source-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for row in checked['manifest']:
            info = zipfile.ZipInfo(name+'/'+row['path'], date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if row['path'] == 'android/gradlew' else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            raw = (root/row['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:raise ValueError('source changed during packaging; freeze and retry')
            stream.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return {'name': name, 'source_sha256': checked['source_sha256'], 'archive': str(archive),
            'source_manifest': str(manifest_path), 'files': checked['manifest']}


def build_wheel(root, output, source):
    """Build only from a clean copied selection, keeping generated files outside source."""
    stage = output.parent/'wheel-sources'/source['source_sha256'][:16]
    stage.mkdir(parents=True, exist_ok=True)
    for row in source['files']:
        target = stage/row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (root/row['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:raise ValueError('source changed before wheel staging')
        target.write_bytes(raw)
    command = [sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps', '--no-build-isolation', '--wheel-dir', str(output), str(stage)]
    completed = subprocess.run(command, cwd=stage, text=True, capture_output=True, timeout=180)
    (output/'wheel-build.log').write_text(completed.stdout+'\n'+completed.stderr, encoding='utf-8')
    if completed.returncode:raise ValueError('wheel build failed; see wheel-build.log')
    candidates = sorted(output.glob('monsieur_cuisine_developer_sdk-*.whl'))
    if len(candidates) != 1:raise ValueError('expected one matching wheel in output')
    return candidates[0]


def verify_wheel(root, output, wheel, *, gui=False, record_windows_launcher_block=False):
    """Install into a new isolated venv and execute outside the checkout."""
    work = Path(tempfile.mkdtemp(prefix='installed-wheel-', dir=output.parent))
    environment_root = work/'venv'
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment_root)
    executable = environment_root/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    command = environment_root/('Scripts/mc-sdk.exe' if os.name=='nt' else 'bin/mc-sdk')
    environment = dict(os.environ)
    environment.pop('PYTHONPATH',None);environment.pop('PYTHONHOME',None)
    environment['PYTHONNOUSERSITE']='1';environment['PYTHONDONTWRITEBYTECODE']='1'
    environment['PIP_DISABLE_PIP_VERSION_CHECK']='1'
    checks = []
    def failed(message):
        (output/'installed-wheel-check.json').write_text(json.dumps({'passed':False,'gui_requested':gui,'checks':checks},indent=2),encoding='utf-8')
        raise ValueError(message)
    def run(arguments, *, launcher=False):
        arguments=[str(x) for x in arguments]
        try:
            done = subprocess.run(arguments,cwd=work,env=environment,capture_output=True,text=True,timeout=120)
        except OSError as exc:
            policy_block = launcher and getattr(exc,'winerror',None)==4551
            checks.append({'command':arguments,'exit_code':None,
                           'status':'blocked_by_windows_appcontrol' if policy_block else 'failed_to_start',
                           'winerror':getattr(exc,'winerror',None),'stdout':'','stderr':str(exc)})
            if policy_block and record_windows_launcher_block:return False
            failed('installed console launcher blocked by Windows policy; see installed-wheel-check.json'
                   if policy_block else 'installed command could not start; see installed-wheel-check.json')
        checks.append({'command':arguments, 'exit_code':done.returncode,
                       'status':'passed' if done.returncode==0 else 'failed',
                       'stdout':done.stdout,'stderr':done.stderr})
        if done.returncode:
            failed('installed wheel check failed; see installed-wheel-check.json')
        return True
    run([executable,'-I','-m','pip','install','--no-index','--no-deps',wheel])
    import inspect
    code = inspect.getsource(mandatory_requirements) + """
import importlib,json,pathlib,re,sys
from monsieur_cuisine_sdk import DigitalTwin,replay
prefix=pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(importlib.import_module('monsieur_cuisine_sdk').__file__).resolve().is_relative_to(prefix)
for model in ('mcc','mcs'):
    twin=DigitalTwin(model,seed=23)
    twin.start_motor(3,direction='ccw',temperature=60)
    twin.advance(.2)
    twin.set_sensors(weight=123,error_code=3)
    twin.stop_motor()
    twin.advance(3)
    assert twin.get_state().actual_speed==0
    assert replay(twin.recording).get_state()==twin.get_state()
for name in ('mcc_protocol','mcs_protocol','mcc_powerboard_simulator','mcs_digital_twin'):
    assert pathlib.Path(importlib.import_module(name).__file__).resolve().is_relative_to(prefix)
assert 'tkinter' not in sys.modules and 'socket' not in sys.modules
import importlib.metadata
declared=importlib.metadata.requires('monsieur-cuisine-developer-sdk') or []
mandatory=mandatory_requirements(declared)
assert not mandatory, mandatory
extras=sorted({m.group(1) for r in declared for m in [re.search(r'extra\\s*==\\s*["\\']([^"\\']+)',r)] if m})
print(json.dumps({'standalone_both_profiles':True,'runtime_dependencies':mandatory,'optional_extras':extras,'installed_under_venv':True}))
"""
    run([executable,'-I','-c',code])
    launcher_blocked=False
    for model in ('mcc','mcs'):
        for tail in (['--model',model,'conformance'],['--model',model,'scenario','start_stop']):
            if launcher_blocked:
                checks.append({'command':[str(command),*tail],'exit_code':None,
                               'status':'not_run_after_windows_policy_block','stdout':'','stderr':''})
                launched=False
            else:
                launched=run([command,*tail],launcher=True)
            if not launched:
                launcher_blocked=True
                # This is the documented Python module invocation. Record it
                # separately; it cannot establish that the blocked EXE passed.
                run([executable,'-I','-m','monsieur_cuisine_sdk.cli',*tail])
        if gui:run([executable,'-I','-m','monsieur_cuisine_sdk','--model',model,'--smoke-test'])
    result={'passed':not launcher_blocked,'functional_checks_passed':True,
            'console_launcher_verified':not launcher_blocked,
            'windows_launcher_policy_blocked':launcher_blocked,
            'module_cli_alternative_executed':launcher_blocked,
            'gui_executed':gui,'new_venv':str(environment_root),'outside_checkout':True,'checks':checks}
    (output/'installed-wheel-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel', action='store_true')
    parser.add_argument('--verify-wheel', action='store_true')
    parser.add_argument('--verify-gui', action='store_true')
    parser.add_argument('--record-windows-launcher-block', action='store_true',
                        help='Local review only: record Windows AppControl error 4551 and check the documented Python module CLI separately; launcher verification remains failed. CI must omit this flag.')
    parser.add_argument('--android-sdk-jar', type=Path)
    parser.add_argument('--demo-apk', type=Path)
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    source = build_source(root, output)
    artifacts = [Path(source['archive']), Path(source['source_manifest'])]
    if args.verify_wheel and not args.wheel:raise ValueError('--verify-wheel requires --wheel')
    if args.verify_gui and not args.verify_wheel:raise ValueError('--verify-gui requires --verify-wheel')
    if args.record_windows_launcher_block and not args.verify_wheel:raise ValueError('--record-windows-launcher-block requires --verify-wheel')
    verification=None
    if args.wheel:
        wheel=build_wheel(root, output, source);artifacts.append(wheel)
        if args.verify_wheel:
            verification=verify_wheel(root,output,wheel,gui=args.verify_gui,
                                      record_windows_launcher_block=args.record_windows_launcher_block)
    for provided, subtree, name in ((args.android_sdk_jar, root/'android/sdk/build/libs', 'monsieur-cuisine-android-sdk.jar'),
                                    (args.demo_apk, root/'android/demo/build/outputs/apk/debug', 'monsieur-cuisine-demo-debug.apk')):
        if provided is None:continue
        original = provided.resolve()
        expected_suffix='.jar' if name.endswith('.jar') else '.apk'
        if not original.is_relative_to(subtree.resolve()) or original.suffix != expected_suffix:
            raise ValueError('binary must come from this project explicit SDK/debug build output')
        if name.endswith('.apk') and 'debug' not in original.name:raise ValueError('only the developer debug APK may be exported')
        target = output/name
        shutil.copyfile(original, target)
        artifacts.append(target)
    records = [{'file': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in artifacts]
    result={'source_sha256': source['source_sha256'], 'artifacts': records}
    if verification is not None:
        result['installed_wheel_verification']={name:verification[name] for name in (
            'passed','functional_checks_passed','console_launcher_verified','windows_launcher_policy_blocked',
            'module_cli_alternative_executed','gui_executed')}
    (output/'ARTIFACT_MANIFEST.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in records), encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':raise SystemExit(main())
