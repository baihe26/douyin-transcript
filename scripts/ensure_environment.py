"""Inspect first; --install builds missing capabilities in separate local venvs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

COMPONENTS = ('ffmpeg', 'ocr', 'asr', 'word', 'collect', 'gpu')
SPECS = {'ffmpeg': ['imageio-ffmpeg>=0.6,<1'],
         'ocr': ['rapidocr>=3.9,<4', 'onnxruntime>=1.16,<2', 'Pillow>=10,<13'],
         'asr': ['funasr>=1.4,<2', 'modelscope>=1.20,<2', 'soundfile>=0.13,<1'],
         'word': ['python-docx>=1.1,<2'], 'collect': ['playwright>=1.40,<2']}


def python_at(directory):
    return directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def redact(value):
    text = re.sub(r'https?://[^\s"\']+', '[URL]', str(value))
    text = re.sub(r'(?i)(authorization|cookie|token|password|secret)\s*[:=]\s*[^\s,]+', '[credential]', text)
    return text[-3000:]


def checked(argv, env, log, timeout=1800):
    log.append({'action': Path(argv[0]).name, 'args': argv[1:]})
    result = subprocess.run(argv, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    log[-1].update(exit_code=result.returncode, output_tail=redact(result.stdout + result.stderr))
    if result.returncode:
        raise RuntimeError('Dependency installation failed; see the local installation log')
    return result.stdout


def inspect(component, python, args, env, download=False):
    argv = [str(python), str(Path(__file__).with_name('runtime_probe.py')), component,
            '--asr-root', str(args.asr_root), '--asr-url', args.asr_url,
            '--gpu-mem-limit', str(args.gpu_mem_limit)]
    for flag, value in (('--gpu-runtime', args.gpu_runtime), ('--ocr-models', args.ocr_models)):
        if value:
            argv += [flag, str(value)]
    if args.verify or args.install or download:
        argv.append('--verify')
    if download:
        argv.append('--download-models')
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=args.timeout)
        matches = [line for line in result.stdout.splitlines() if line.startswith('DOUYIN_PROBE_JSON=')]
        payload = json.loads(matches[-1].split('=', 1)[1]) if matches else {
            'status': 'failed', 'reason': 'probe_process_failed',
            'diagnostic': redact(result.stdout + result.stderr)}
    except subprocess.TimeoutExpired:
        payload = {'status': 'failed', 'reason': 'probe_timeout', 'timeout_seconds': args.timeout}
    except OSError as exc:
        payload = {'status': 'missing', 'reason': type(exc).__name__}
    if 'diagnostic' in payload:
        payload['diagnostic'] = redact(payload['diagnostic'])
    payload['python'] = str(python)
    return payload


def lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'environment-install.lock'
    # Atomic exclusive creation. Stale lock: inspect PID before manually removing.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--components', default='ffmpeg,asr,ocr')
    parser.add_argument('--tool-python', type=Path)
    parser.add_argument('--extra-python', type=Path, action='append', default=[],
                        help='Additional known local runtimes to reuse, repeatable')
    parser.add_argument('--asr-root', type=Path)
    parser.add_argument('--asr-url', default='http://127.0.0.1:18080')
    parser.add_argument('--ocr-models', type=Path)
    parser.add_argument('--gpu-runtime', type=Path)
    parser.add_argument('--gpu-mem-limit', type=int, default=1073741824)
    parser.add_argument('--gpu-spec', help='Official ORT spec chosen against the current CUDA compatibility matrix')
    parser.add_argument('--verify', action='store_true', help='Run only local synthetic inference/decoder checks')
    parser.add_argument('--install', action='store_true', help='Install missing capabilities into isolated venvs')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--output', type=Path, help='Write a private local JSON report')
    args = parser.parse_args()
    args.root = args.root.expanduser().resolve()
    if not args.root.is_dir():
        parser.error('--root must be an existing selected workspace; this does not install the collector')
    components = list(dict.fromkeys(args.components.split(',')))
    if not components or any(c not in COMPONENTS for c in components):
        parser.error('components must be a comma-separated subset of ' + ','.join(COMPONENTS))
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    if args.gpu_spec and not re.fullmatch(r'onnxruntime-gpu(?:\[(?:cuda,cudnn|cudnn,cuda)\])?==\d+\.\d+\.\d+', args.gpu_spec):
        parser.error('--gpu-spec requires a pinned official onnxruntime-gpu release, optionally [cuda,cudnn]')
    from runtime_probe import local_url
    local_url(args.asr_url)
    runtime = args.root / '.skill-runtime'
    existing_asr = [args.root.parent / 'CX_funasr_local', Path(args.root.anchor) / 'CX_funasr_local']
    inferred_asr = next((p for p in existing_asr if python_at(p / '.venv').is_file()), runtime / 'asr')
    args.asr_root = (args.asr_root or Path(os.environ.get('DOUYIN_FUNASR_ROOT',
                     str(inferred_asr)))).expanduser().resolve()
    default_tool = python_at(args.root / '.venv')
    args.tool_python = args.tool_python or (default_tool if default_tool.is_file() else Path(sys.executable))
    if not args.gpu_runtime:
        existing_gpu = args.root / '.state' / 'gpu_runtime'
        managed_gpu = runtime / 'gpu' / ('Lib/site-packages' if os.name == 'nt' else
                      f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
        args.gpu_runtime = next((p for p in (existing_gpu, managed_gpu)
                                 if (p / 'onnxruntime').is_dir()), None)
    # Read healthy settings; never overwrite GPU configuration or live device status.
    settings_path = args.root / '.state' / 'gpu_ocr.json'
    if settings_path.is_file():
        config = json.loads(settings_path.read_text(encoding='utf-8-sig'))
        args.gpu_mem_limit = int(config.get('gpu_mem_limit', args.gpu_mem_limit))
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(args.root / '.cache' / 'ms-playwright')
    env['MODELSCOPE_CACHE'] = str(args.asr_root / 'models')
    # Inspection itself creates neither venvs nor model-cache directories.
    checks = {}
    log = []
    install_lock = None
    try:
        for component in components:
            managed = python_at(runtime / component)
            preferred = python_at(args.asr_root / '.venv') if component == 'asr' else args.tool_python
            candidates = [p for p in (preferred, managed, *args.extra_python, Path(sys.executable)) if p.is_file()]
            checks[component] = {'status': 'missing', 'reason': 'python_not_found'}
            for candidate in dict.fromkeys(candidates):
                check = inspect(component, candidate, args, env)
                checks[component] = check
                if check['status'] in {'ready', 'detected'}:
                    break
                # A functioning package with runtime failure needs diagnosis, not another installation.
                if check['status'] == 'failed':
                    break
            if not args.install or checks[component]['status'] != 'missing':
                continue
            if component in {'ocr', 'gpu'} and args.ocr_models:
                from runtime_probe import models_in
                if not models_in(args.ocr_models):
                    checks[component]['reason'] = 'explicit_model_directory_missing_or_ambiguous_fix_configuration'
                    continue
            if install_lock is None:
                install_lock = lock(runtime)
                if shutil.disk_usage(args.root).free < 5 * 1024**3:
                    raise RuntimeError('Less than 5 GiB free; preserve existing data and clear the capacity issue first')
            if component == 'gpu' and not args.gpu_spec:
                checks[component]['reason'] = 'choose_official_cuda_compatible_gpu_spec_before_install'
                continue
            if not managed.is_file():
                checked([sys.executable, '-m', 'venv', str(runtime / component)], env, log)
            packages = list(SPECS.get(component, []))
            if component == 'asr':
                checked([str(managed), '-m', 'pip', 'install', '--index-url',
                         'https://download.pytorch.org/whl/cpu', 'torch', 'torchaudio'], env, log)
            if component == 'gpu':
                packages = ['rapidocr>=3.9,<4', 'Pillow>=10,<13', args.gpu_spec]
                args.gpu_runtime = runtime / 'gpu' / ('Lib/site-packages' if os.name == 'nt' else
                    f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
            checked([str(managed), '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple',
                     '--timeout', '60', '--retries', '1', *packages], env, log)
            if component == 'collect':
                checked([str(managed), '-m', 'playwright', 'install', 'chromium'], env, log)
            # Weights download is explicit within --install, only for required local ASR/OCR.
            checks[component] = inspect(component, managed, args, env,
                                        download=component in {'asr', 'ocr', 'gpu'})
            versions = checked([str(managed), '-m', 'pip', 'freeze', '--all'], env, log, timeout=60)
            (runtime / component / 'installed-versions.txt').write_text(
                versions, encoding='utf-8')
            checks[component]['installed_isolated'] = True
    except FileExistsError:
        checks['installer'] = {'status': 'failed', 'reason': 'another_installer_or_stale_lock_inspect_pid_first'}
    except Exception as exc:
        checks['installer'] = {'status': 'failed', 'reason': type(exc).__name__, 'diagnostic': redact(exc)}
    finally:
        if install_lock:
            install_lock.unlink(missing_ok=True)
    report = {'schema': 'douyin-environment-v1', 'time': datetime.now(timezone.utc).isoformat(),
              'requested_components': components, 'verified': args.verify or args.install,
              'ready': all(c['status'] == 'ready' for c in checks.values()), 'checks': checks,
              'integration_note': 'Use each reported python in the matching stage; run tool doctor before collecting. '
                                  'Package readiness alone does not prove collector adapter/login/whole-batch readiness.',
              'installation_log': log}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + '.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
