"""Read-only artifact audit. --write-monitor explicitly enables local report writes."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

SCHEMA = 'douyin-artifact-audit-v1'
TERMINAL = {'complete', 'ocr_complete', 'ocr_skipped'}

def read_json(path, optional=False):
    if optional and not path.exists():
        return {}
    for attempt in range(5):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (json.JSONDecodeError, PermissionError):
            if attempt == 4:
                raise
            time.sleep(0.3)

def within(base, value):
    p = (base / str(value)).resolve()
    if not p.is_relative_to(base.resolve()):
        raise ValueError('Artifact outside the selected job')
    return p

def canonical(url, fallback):
    match = re.search(r'/(?:video|note)/(\d+)', str(url))
    return match.group(1) if match else str(fallback)

def safe_message(value):
    text = str(value or '')
    text = re.sub(r'https?://\S+', '[URL隐去]', text)
    text = re.sub(r'(?i)(?:cookie|authorization|[A-Za-z_]*token|secret)\s*[:=].*', '[凭据字段隐去]', text)
    text = re.sub(r'\b(?:sk|ghp|github_pat)-[A-Za-z0-9_-]{16,}', '[凭据隐去]', text)
    return text[-1500:]

def tail(path):
    if not path.exists():
        return []
    with path.open('rb') as fp:
        fp.seek(max(0, path.stat().st_size - 8192))
        lines = fp.read().decode('utf-8', errors='replace').splitlines()
    return [safe_message(line) for line in lines[-6:]]

def processes(submission):
    if os.name != 'nt':
        return {'available': False, 'reason': 'Windows process inventory not available'}
    # Print metadata only, never raw command lines. Script + exact argv token select workers.
    names = ['CX_process_saved_local.py', 'CX_save_remaining_media.py', 'chrome_process_batch.py']
    script = ("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | "
              "Where-Object { $_.Name -match '^python(w)?\\.exe$' } | "
              "Select-Object ProcessId,ParentProcessId,CommandLine,KernelModeTime,UserModeTime | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, timeout=30, check=True)
        rows = json.loads(result.stdout.decode('utf-8-sig', errors='replace') or '[]')
        if isinstance(rows, dict):
            rows = [rows]
        selected = []
        for row in rows:
            cmd = row.get('CommandLine') or ''
            argv = re.findall(r'"([^"]*)"|(\S+)', cmd)
            tokens = [a or b for a, b in argv]
            if submission not in tokens:
                continue
            for name in names:
                if not any(Path(t).name == name for t in tokens):
                    continue
                selected.append({'script': name, 'pid': row['ProcessId'],
                                 'parent_pid': row['ParentProcessId'],
                                 'cpu_seconds': (int(row.get('KernelModeTime') or 0) +
                                                 int(row.get('UserModeTime') or 0)) / 10000000})
        for row in selected:
            row['worker_root_pid'] = row['pid']
            seen = set()
            while row['worker_root_pid'] not in seen:
                seen.add(row['worker_root_pid'])
                current = next((x for x in selected if x['pid'] == row['worker_root_pid']), None)
                parent = next((x for x in selected if current and x['pid'] == current['parent_pid']
                               and x['script'] == row['script']), None)
                if not parent:
                    break
                row['worker_root_pid'] = parent['pid']
        counts = Counter(name for name, _ in {(x['script'], x['worker_root_pid']) for x in selected})
        return {'available': True, 'rows': selected, 'worker_trees': dict(counts)}
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        return {'available': False, 'reason': type(exc).__name__}

def audit(root, job_name, submission):
    job = within(root / 'jobs', job_name)
    folder = within(root / '.state/submissions', submission)
    status = read_json(folder / 'status.json')
    if status.get('job') != job_name:
        raise ValueError('Submission job does not match the requested job')
    manifest = read_json(job / 'source_manifest.json')
    config = read_json(job / 'job.json', optional=True)
    items = read_json(job / 'items.json')
    if not isinstance(items, list):
        raise ValueError('items.json must be a list')
    rows = manifest.get('videos', [])
    source_ids = {canonical(x.get('url'), x.get('id')) for x in rows}
    item_ids = [canonical(x.get('original_url'), x.get('id')) for x in items]
    if not source_ids or len(item_ids) != len(set(item_ids)) or set(item_ids) != source_ids:
        raise ValueError('Fixed manifest and item identities do not match; refusing completion counts')
    by_internal = {str(x['id']): aid for x, aid in zip(items, item_ids)}
    latest = {}
    def file_ok(value, nonempty=True, kind=None):
        try:
            p = within(job, value)
            if not p.is_file():
                return False
            stat = p.stat()
            if nonempty and stat.st_size <= 0:
                return False
            if kind:
                latest[kind] = max(latest.get(kind, 0), stat.st_mtime)
            return True
        except (OSError, ValueError):
            return False
    saved = set()
    invalid_registered = []
    def media_ok(item, files):
        directory = within(job, Path('downloaded') / item['id'])
        return bool(files) and all(within(job, f).is_relative_to(directory)
                                   and file_ok(f, kind='media') for f in files)
    for item, aid in zip(items, item_ids):
        files = item.get('video_files', []) + item.get('image_files', []) + item.get('source_cover_files', [])
        if media_ok(item, files):
            saved.add(aid)
        elif files:
            invalid_registered.append(aid)
    media = read_json(folder / 'media_stage.json', optional=True)
    missing_staged, out_of_scope = [], []
    item_by_internal = {str(x['id']): x for x in items}
    for row in media.get('completed', []):
        aid = by_internal.get(str(row.get('item_id')))
        if aid is None:
            out_of_scope.append(str(row.get('item_id')))
            continue
        files = row.get('files', [])
        if media_ok(item_by_internal[str(row['item_id'])], files):
            saved.add(aid)
        else:
            missing_staged.append(aid)
    counts = Counter()
    issues = []
    ocr_enabled = config.get('visual', {}).get('ocr_enabled', True)
    for item, aid in zip(items, item_ids):
        tids = item.get('transcript_ids', [])
        for tid in tids:
            within(job / 'transcripts', tid)  # Reject traversal even in incomplete metadata.
        speech_paths = [Path('transcripts') / tid / 'transcript.txt' for tid in tids]
        speech_ok = bool(tids) and all(file_ok(p, kind='speech') for p in speech_paths)
        counts['speech_artifacts'] += speech_ok
        media_kind = item.get('media_kind') or ('image' if item.get('image_files') else 'video')
        counts['image_speech_placeholders'] += speech_ok and media_kind == 'image'
        counts['asr_artifacts'] += speech_ok and media_kind != 'image'
        has_placeholder = False
        if speech_ok:
            for p in speech_paths:
                with within(job, p).open(encoding='utf-8-sig') as fp:
                    head = fp.read(160).strip()
                if head.startswith('[未检测到可转写语音]'):
                    has_placeholder = True
            counts['no_speech_works'] += has_placeholder
        screen_paths = [Path('transcripts') / tid / 'visual/screen_text.txt' for tid in tids]
        ocr_ok = bool(tids) and all(file_ok(p, nonempty=False, kind='ocr') for p in screen_paths)
        ocr_state = item.get('status') == 'ocr_complete' or item.get('ocr_status') == 'complete'
        counts['ocr_complete'] += ocr_ok and ocr_state
        if ocr_ok and ocr_state:
            no_text = True
            for p in screen_paths:
                with within(job, p).open(encoding='utf-8-sig') as fp:
                    head = fp.read(160).strip()
                if head and not head.startswith('未识别到可信'):
                    no_text = False
            counts['ocr_without_text'] += no_text
        terminal = item.get('status') in TERMINAL
        applicable_speech = media_kind == 'image' or speech_ok
        applicable_ocr = not ocr_enabled or (ocr_ok and ocr_state)
        counts['complete'] += terminal and aid in saved and applicable_speech and applicable_ocr
        analyses, cards_ok = [], bool(tids)
        for tid in tids:
            ap = within(job, Path('transcripts') / tid / 'analysis.json')
            analysis = read_json(ap, optional=True)
            analyses.append(analysis.get('status'))
            card_ok = file_ok(Path('transcripts') / tid / '整理卡.md', kind='classification')
            cards_ok = cards_ok and card_ok
        counts['classified'] += bool(tids) and cards_ok and all(s == 'complete' for s in analyses)
        counts['analysis_failed'] += 'failed' in analyses
        counts['extraction_failed'] += str(item.get('status', '')).endswith('_failed')
        counts['unsupported'] += item.get('status') == 'unsupported'
        if terminal and not (aid in saved and applicable_speech and applicable_ocr):
            issues.append(aid)
    result = {'counter_schema': SCHEMA, 'checked_at': datetime.now().astimezone().isoformat(),
              'job': job_name, 'submission': submission, 'scope_total': len(source_ids),
              'collection_complete': manifest.get('complete'), 'source_count_gaps': manifest.get('count_gaps', []),
              'media_saved': len(saved), 'awaiting_download': len(source_ids) - len(saved),
              **{k: counts[k] for k in ('complete', 'speech_artifacts', 'asr_artifacts',
                                       'image_speech_placeholders', 'no_speech_works', 'ocr_complete',
                                       'ocr_without_text', 'classified', 'analysis_failed',
                                       'extraction_failed', 'unsupported')},
              'item_states': dict(Counter(x.get('status') for x in items)),
              'missing_registered': invalid_registered, 'missing_staged': sorted(set(missing_staged)),
              'out_of_scope_staged': out_of_scope, 'terminal_artifact_issues': issues,
              'media_state': media.get('state'), 'media_stage': media.get('stage'),
              'media_error': safe_message(media.get('error')), 'local_state': status.get('state'),
              'local_mode': status.get('mode'), 'local_stage': status.get('result', {}).get('stage'),
              'local_error': safe_message(status.get('local_error')),
              'latest_artifacts': {k: datetime.fromtimestamp(v, timezone.utc).isoformat() for k, v in latest.items()},
              'ocr_device': read_json(root / '.state/ocr_device.json', optional=True),
              'log_tail': {'local': tail(folder / 'worker.log'), 'media': tail(folder / 'media_worker.log')}}
    # Device and log exceptions may embed signed URLs; sanitize before output.
    if result['ocr_device'].get('reason'):
        result['ocr_device']['reason'] = safe_message(result['ocr_device']['reason'])
    result['ocr_device_scope_note'] = 'GPU状态为工具全局记录，须与当前worker PID核对'
    return result, folder

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--submission', required=True)
    parser.add_argument('--processes', action='store_true')
    parser.add_argument('--write-monitor', action='store_true')
    args = parser.parse_args()
    for name in (args.job, args.submission):
        if not re.fullmatch('[A-Za-z0-9_-]+', name):
            parser.error('job/submission must be simple local identifiers')
    result, folder = audit(args.root.resolve(), args.job, args.submission)
    if args.processes:
        result['processes'] = processes(args.submission)
    if args.write_monitor:
        target = folder / 'monitor_latest.json'
        old = read_json(target, optional=True)
        compatible = (old.get('counter_schema') == SCHEMA and old.get('job') == args.job
                      and old.get('submission') == args.submission)
        result['delta_baseline_compatible'] = compatible
        result['delta'] = {key: result[key] - old[key] for key in
                           ('complete', 'media_saved', 'speech_artifacts', 'ocr_complete', 'classified')
                           if compatible and key in old}
        temp = target.with_name('monitor_latest.' + str(os.getpid()) + '.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, target)
        with (folder / 'monitor_history.jsonl').open('a', encoding='utf-8') as fp:
            fp.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
