"""Offline, resumable eight-group migration. Reuses features without decoding videos.

Stop the web server first. Run without --apply to save and inspect the plan;
then run with --apply --run-dir <the saved directory>. Keep that directory.
"""
import argparse
import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils.video_similarity.cache import FeatureCache
from utils.video_similarity.features import VideoFeatures

BOUNDS = [0, 2048, 4096, 6144, 8192, 12288, 16384, 32768, None]
NAMES = ['01_0-2MiB', '02_2-4MiB', '03_4-6MiB', '04_6-8MiB',
         '05_8-12MiB', '06_12-16MiB', '07_16-32MiB', '08_32MiB-plus']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.regroup-tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def resolve(value):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def checked(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f'Path outside allowed root: {path}')
    return path


def path_key(path):
    return str(Path(path).resolve()).casefold()


def identity(path):
    return list(FeatureCache._identity(Path(path).stat()))


def group_index(size):
    size_kib = (size + 1023) // 1024
    return next(i for i in range(8) if BOUNDS[i + 1] is None or size_kib < BOUNDS[i + 1])


def reserve_target(target, reserved):
    candidate, suffix = target, 0
    while path_key(candidate) in reserved or candidate.exists():
        suffix += 1
        candidate = target.with_name(f'{target.stem}_{suffix}{target.suffix}')
    reserved.add(path_key(candidate))
    return candidate


def remap_records(report, dismissed, mapping):
    report, dismissed = copy.deepcopy(report), copy.deepcopy(dismissed)
    def remap(path):
        return mapping.get(path_key(path), path)
    for group in report:
        for video in group.get('videos', []):
            old = video.get('originalPath')
            if old and path_key(old) in mapping:
                video['originalPath'] = remap(old)
                video['path'] = '/stream/' + quote(remap(old))
                video['name'] = Path(remap(old)).name
    decisions = {}
    for old_id, entry in dismissed.get('dismissed', {}).items():
        paths = entry.get('paths')
        if not paths:
            decisions[old_id] = entry
            continue
        entry['paths'] = sorted(remap(p) for p in paths)
        new_id = hashlib.sha256('|'.join(entry['paths']).encode('utf-8')).hexdigest()[:16]
        if new_id in decisions:
            raise ValueError('Remapping would merge ignored decisions')
        decisions[new_id] = entry
    dismissed['dismissed'] = decisions
    return report, dismissed


def make_plan(config_file, run_dir):
    cfg = read_json(config_file)
    archive, downloads = resolve(cfg['archive_base_dir']), resolve(cfg['download_dir'])
    extensions = set(e.lower() for e in cfg['video_extensions'])
    # Download queues need their own cross-volume workflow; never silently leave videos behind.
    for name in cfg['categories']:
        folder = checked(downloads / name, downloads)
        if folder.exists() and any(p.is_file() and p.suffix.lower() in extensions for p in folder.rglob('*')):
            raise ValueError(f'Finish processing the download category first: {folder}')
    if cfg.get('base_dirs') or cfg.get('incremental_dirs'):
        raise ValueError('Explicit comparison directories require a separate mapping')
    sources = sorted((checked(p, archive) for p in archive.rglob('*')
                      if p.is_file() and p.suffix.lower() in extensions), key=path_key)
    if len({path_key(p) for p in sources}) != len(sources):
        raise ValueError('Duplicate resolved source paths')
    cache = FeatureCache(resolve(cfg['cache_dir']))
    entries, counts, reserved = [], [0] * 8, set()
    for source in sources:
        stat_id = identity(source)
        group = group_index(stat_id[0])
        target = checked(reserve_target(archive / NAMES[group] / source.name, reserved), archive)
        if source.stat().st_dev != archive.stat().st_dev:
            raise ValueError('Only same-volume archive moves are supported')
        entries.append({'source': str(source), 'target': str(target), 'identity': stat_id,
                        'old_cache_id': cache._get_cache_id(source),
                        'new_cache_id': cache._get_cache_id(target), 'group': group})
        counts[group] += 1
    if len({e['new_cache_id'] for e in entries}) != len(entries):
        raise ValueError('Cache key collision')
    new_cfg = copy.deepcopy(cfg)
    new_cfg['categories'] = {name: {'size_range_kb': BOUNDS[i:i+2], 'archive_subdir': name}
                             for i, name in enumerate(NAMES)}
    plan = {'created_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'config_file': str(config_file),
            'original_config': cfg, 'new_config': new_cfg, 'entries': entries,
            'counts': counts, 'total_bytes': sum(e['identity'][0] for e in entries),
            'renamed_collisions': sum(Path(e['source']).name != Path(e['target']).name for e in entries)}
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / 'plan.json', plan)
    print(json.dumps({k: plan[k] for k in ('counts', 'total_bytes', 'renamed_collisions')}) , flush=True)
    return plan


def feature_payload(data):
    result = VideoFeatures.from_dict(data).to_dict()
    result.pop('file_path')
    return result


def progress(stage, done, total, started):
    if done % 250 == 0 or done == total:
        print(f'{stage}: {done}/{total}; elapsed {time.perf_counter()-started:.1f}s', flush=True)


def apply_plan(plan, run_dir):
    started = time.perf_counter()
    cfg, entries = plan['original_config'], plan['entries']
    archive, downloads = resolve(cfg['archive_base_dir']), resolve(cfg['download_dir'])
    cache = FeatureCache(resolve(cfg['cache_dir']))
    output = resolve(cfg['output_dir'])
    backup = run_dir / 'backup'
    backup.mkdir(exist_ok=True)
    old_cache = backup / 'features'
    old_cache.mkdir(exist_ok=True)
    profile = {'algorithm': 1, **{k: cfg['similarity'][k] for k in ('num_sample_frames', 'hash_size', 'hist_bins')}}
    # Complete ALL checks/backups before any rename. This marker makes retries idempotent.
    if not (run_dir / 'backup-complete.json').exists():
        if read_json(plan['config_file']) != cfg:
            raise ValueError('Configuration changed since planning')
        for name, source in [('config.json', Path(plan['config_file'])),
                             ('data.json', output / 'data.json'), ('dismissed.json', output / 'dismissed.json')]:
            if source.exists():
                shutil.copy2(source, backup / name)
        with closing(sqlite3.connect(cache.index_path)) as source_db, closing(sqlite3.connect(backup / cache.INDEX_NAME)) as target_db:
            source_db.backup(target_db)
        for i, entry in enumerate(entries, 1):
            source, target = checked(entry['source'], archive), checked(entry['target'], archive)
            if identity(source) != entry['identity'] or target.exists():
                raise ValueError(f'Source changed or target exists: {source}')
            feature = cache.get(source, profile)
            if feature is None:
                raise ValueError(f'No reusable feature cache: {source}')
            row = cache._row(entry['old_cache_id'])
            if not row or not row['sha256'] or not cache._same_file(row, source.stat()):
                raise ValueError(f'Content index not ready: {source}')
            shutil.copy2(cache.cache_dir / (entry['old_cache_id'] + '.json'), old_cache)
            progress('Backup and preflight', i, len(entries), started)
        write_json(run_dir / 'backup-complete.json', {'count': len(entries)})
    for name in NAMES:
        checked(archive / name, archive).mkdir(exist_ok=True)
        checked(downloads / name, downloads).mkdir(exist_ok=True)
    with (run_dir / 'journal.jsonl').open('a', encoding='utf-8') as journal:
        for i, entry in enumerate(entries, 1):
            source, target = checked(entry['source'], archive), checked(entry['target'], archive)
            if source.exists():
                if target.exists() or identity(source) != entry['identity']:
                    raise ValueError(f'Move conflict: {source}')
                source.rename(target)  # Windows rename never overwrites an existing destination.
            if not target.is_file() or identity(target) != entry['identity']:
                raise ValueError(f'Moved file identity mismatch: {target}')
            feature = cache.get(target, profile)
            original = read_json(old_cache / (entry['old_cache_id'] + '.json'))
            if feature is None or feature_payload(feature.to_dict()) != feature_payload(original):
                raise ValueError(f'Feature reuse failed: {target}. Resume using the same --run-dir.')
            journal.write(json.dumps({'source': str(source), 'target': str(target), 'cache_verified': True}) + '\n')
            journal.flush()
            if i % 250 == 0 or i == len(entries):
                os.fsync(journal.fileno())
            progress('Moved and cache verified', i, len(entries), started)
    actual = {path_key(p) for p in archive.rglob('*') if p.is_file() and p.suffix.lower() in cfg['video_extensions']}
    expected = {path_key(e['target']) for e in entries}
    if actual != expected:
        raise ValueError('Archive inventory changed during migration')
    mapping = {path_key(e['source']): e['target'] for e in entries}
    report, dismissed = remap_records(read_json(backup / 'data.json') if (backup / 'data.json').exists() else [],
                                     read_json(backup / 'dismissed.json') if (backup / 'dismissed.json').exists() else {'version': 1, 'dismissed': {}}, mapping)
    write_json(output / 'data.json', report)
    write_json(output / 'dismissed.json', dismissed)
    write_json(plan['config_file'], plan['new_config'])
    # Retire old path JSONs into the backup, never delete them or any unrelated cache.
    retired = backup / 'retired-path-cache'
    retired.mkdir(exist_ok=True)
    new_ids = {e['new_cache_id'] for e in entries}
    for entry in entries:
        old_id = entry['old_cache_id']
        old_file = checked(cache.cache_dir / (old_id + '.json'), cache.cache_dir)
        if old_id not in new_ids and old_file.exists():
            old_file.rename(retired / old_file.name)
    with cache._db() as db:
        db.executemany('DELETE FROM entries WHERE cache_id=?',
                       [(e['old_cache_id'],) for e in entries if e['old_cache_id'] not in new_ids])
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        indexed = db.execute('SELECT count(*) FROM entries WHERE sha256 IS NOT NULL').fetchone()[0]
    retained_dirs = []
    for name, details in cfg['categories'].items():
        for root, folder in [(archive, archive / details['archive_subdir']), (downloads, downloads / name)]:
            folder = checked(folder, root)
            if folder.exists() and folder.name not in NAMES:
                try:
                    folder.rmdir()  # Empty directories only; preserve sidecars and other files.
                except OSError:
                    retained_dirs.append(str(folder))
    result = {'success': True, 'videos': len(entries), 'total_bytes': plan['total_bytes'],
              'groups': dict(zip(NAMES, plan['counts'])), 'collision_renames': plan['renamed_collisions'],
              'features_reused': len(entries), 'videos_decoded': 0,
              'dismissed_preserved': len(dismissed['dismissed']), 'sqlite_integrity': integrity,
              'full_digest_entries': indexed, 'retained_old_dirs': retained_dirs,
              'seconds': round(time.perf_counter()-started, 2)}
    if integrity != 'ok':
        raise ValueError('Cache index integrity check failed')
    write_json(run_dir / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/video_processor.json')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    run_dir = (args.run_dir or ROOT / 'output' / time.strftime('regroup-8-%Y%m%d-%H%M%S')).resolve()
    plan_path = run_dir / 'plan.json'
    plan = read_json(plan_path) if plan_path.exists() else make_plan(args.config.resolve(), run_dir)
    print(f'Migration directory: {run_dir}', flush=True)
    if args.apply:
        apply_plan(plan, run_dir)


if __name__ == '__main__':
    main()
