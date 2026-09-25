"""Versioned feature records with a rebuildable content/identity index."""
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from dataclasses import replace
from .features import VideoFeatures


class FeatureCache:
    INDEX_NAME = 'content-index.sqlite3'
    SCHEMA_VERSION = 2

    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / 'cache' / 'video_similarity')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / self.INDEX_NAME
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS entries (
                    cache_id TEXT PRIMARY KEY, path TEXT NOT NULL,
                    size INTEGER, mtime_ns INTEGER, device TEXT, inode TEXT,
                    fingerprint TEXT, sha256 TEXT,
                    cache_size INTEGER, cache_mtime_ns INTEGER);
                CREATE INDEX IF NOT EXISTS by_fingerprint ON entries(fingerprint);
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.index_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=NORMAL')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _identity(stat):
        return (stat.st_size, stat.st_mtime_ns, str(stat.st_dev), str(stat.st_ino))

    @classmethod
    def _same_file(cls, row, stat):
        return bool(stat.st_ino and tuple(row[k] for k in ('size', 'mtime_ns', 'device', 'inode')) == cls._identity(stat))

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()

    def get_file_hash(self, file_path):
        """Quick fingerprint: prefilter only for cross-path lookup."""
        try:
            path = Path(file_path)
            size = path.stat().st_size
            digest = hashlib.md5(str(size).encode())
            with path.open('rb') as stream:
                digest.update(stream.read(65536))
                if size > 131072:
                    stream.seek(-65536, 2)
                    digest.update(stream.read(65536))
            return digest.hexdigest()
        except OSError:
            return ''

    @staticmethod
    def _get_cache_id(video_path):
        return hashlib.md5(str(Path(video_path).resolve()).encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def _read(path):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if (data.get('_cache_version') != FeatureCache.SCHEMA_VERSION
                    or not isinstance(data.get('_cache_profile'), dict)
                    or set(data['_cache_profile']) != {'algorithm', 'num_sample_frames', 'hash_size', 'hist_bins'}
                    or not all(type(v) is int and v > 0 for v in data['_cache_profile'].values())
                    or not isinstance(data.get('_content_sha256'), str)
                    or len(data['_content_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in data['_content_sha256'])):
                return None
            feature = VideoFeatures.from_dict(data)
            if not feature.phashes or not (len(feature.phashes) == len(feature.dhashes) == len(feature.histograms)):
                return None
            return data
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    @staticmethod
    def _matches_profile(data, profile):
        return profile is None or data['_cache_profile'] == profile

    def _row(self, cache_id):
        with self._db() as db:
            return db.execute('SELECT * FROM entries WHERE cache_id=?', (cache_id,)).fetchone()

    def _record(self, path, data, stat, sha256=None):
        cache_id = self._get_cache_id(path)
        cache_stat = (self.cache_dir / (cache_id + '.json')).stat()
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (cache_id, str(path), *self._identity(stat), data['file_hash'], sha256,
                        cache_stat.st_size, cache_stat.st_mtime_ns))

    @staticmethod
    def _unchanged_cache(row, cache_file):
        try:
            stat = cache_file.stat()
            return (stat.st_size, stat.st_mtime_ns) == (row['cache_size'], row['cache_mtime_ns'])
        except OSError:
            return False

    def rebuild_index(self, full_hash=False, progress=None):
        """Validate current-format records and rebuild lookup entries; never decode."""
        files = list(self.cache_dir.glob('*.json'))
        result = {'indexed': 0, 'skipped': 0, 'errors': [], 'total': len(files)}
        for i, cache_file in enumerate(files):
            try:
                data = self._read(cache_file)
                if data is None:
                    result['skipped'] += 1
                    continue
                path = Path(data['file_path']).resolve()
                if cache_file.stem != self._get_cache_id(path) or not path.is_file():
                    result['skipped'] += 1
                    continue
                stat = path.stat()
                row = self._row(cache_file.stem)
                ready = (row and self._same_file(row, stat) and self._unchanged_cache(row, cache_file)
                         and row['sha256'] == data['_content_sha256'])
                if (self.get_file_hash(path) != data['file_hash']
                        or ((full_hash or not ready) and self._sha256(path) != data['_content_sha256'])):
                    result['skipped'] += 1
                    continue
                if self._identity(path.stat()) != self._identity(stat):
                    raise OSError('Video changed while indexing')
                self._record(path, data, stat, data['_content_sha256'])
                result['indexed'] += 1
            except (OSError, ValueError, sqlite3.Error) as exc:
                result['errors'].append({'cache': cache_file.name, 'error': str(exc)})
            finally:
                if progress:
                    progress(i + 1, len(files))
        return result

    def _lookup(self, video_path, profile=None, materialize=True):
        path = Path(video_path).resolve()
        try:
            stat = path.stat()
            fingerprint = self.get_file_hash(path)
            if not fingerprint:
                return None, None
            cache_id = self._get_cache_id(path)
            cache_file = self.cache_dir / (cache_id + '.json')
            data = self._read(cache_file)
            row = self._row(cache_id)
            if data and data['file_hash'] == fingerprint and self._matches_profile(data, profile):
                if not (row and self._same_file(row, stat) and self._unchanged_cache(row, cache_file)
                        and row['sha256'] == data['_content_sha256']):
                    if self._sha256(path) != data['_content_sha256']:
                        return None, None
                    self._record(path, data, stat, data['_content_sha256'])
                if self._identity(path.stat()) != self._identity(stat):
                    return None, None
                return replace(VideoFeatures.from_dict(data), file_path=str(path)), cache_id
            with self._db() as db:
                candidates = db.execute('SELECT * FROM entries WHERE fingerprint=?', (fingerprint,)).fetchall()
            candidates = sorted(candidates, key=lambda r: not self._same_file(r, stat))
            target_sha = None
            for candidate in candidates:
                source_cache = self.cache_dir / (candidate['cache_id'] + '.json')
                if not self._unchanged_cache(candidate, source_cache):
                    continue
                source_data = self._read(source_cache)
                if not source_data or not self._matches_profile(source_data, profile):
                    continue
                sha = source_data['_content_sha256']
                if sha != candidate['sha256']:
                    continue
                if not self._same_file(candidate, stat):
                    if target_sha is None:
                        target_sha = self._sha256(path)
                    if target_sha != sha:
                        continue
                if self._identity(path.stat()) != self._identity(stat):
                    return None, None
                features = replace(VideoFeatures.from_dict(source_data), file_path=str(path))
                if materialize:
                    self._write(features, source_data['_cache_profile'], sha, stat)
                return features, cache_id if materialize else candidate['cache_id']
            return None, None
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            return None, None

    def get(self, video_path, profile=None):
        return self._lookup(video_path, profile)[0]

    def referenced_cache_ids(self, video_paths, candidate_ids=None):
        # Dry-run cleanup must keep old-path JSONs still backing moved videos.
        if candidate_ids is not None:
            if not candidate_ids:
                return set()
            # Cross-path lookup can only reuse indexed entries of identical size.
            # Avoid loading every feature record when only a few paths are orphaned.
            with self._db() as db:
                sizes = {row['size'] for row in db.execute('SELECT cache_id, size FROM entries')
                         if row['cache_id'] in candidate_ids}
            matching_paths = []
            for path in video_paths:
                try:
                    if Path(path).stat().st_size in sizes:
                        matching_paths.append(path)
                except OSError:
                    continue
            video_paths = matching_paths
        return {cache_id for path in video_paths
                for feature, cache_id in [self._lookup(path, materialize=False)]
                if feature is not None}

    def _write(self, features, profile, sha256, stat):
        data = features.to_dict()
        if profile is None or not sha256:
            raise ValueError('Cache writes require an extraction profile and content digest')
        data['_cache_version'] = self.SCHEMA_VERSION
        data['_cache_profile'] = profile
        data['_content_sha256'] = sha256
        target = self.cache_dir / (self._get_cache_id(features.file_path) + '.json')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.cache_dir,
                                             prefix=target.stem + '-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False)
            # Windows readers can briefly deny rename/delete sharing.
            for attempt in range(10):
                try:
                    temporary.replace(target)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(.01 * (attempt + 1))
            self._record(Path(features.file_path).resolve(), data, stat, sha256)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def set(self, features, profile):
        try:
            path = Path(features.file_path).resolve()
            stat = path.stat()
            sha = self._sha256(path)
            if self.get_file_hash(path) != features.file_hash or self._identity(path.stat()) != self._identity(stat):
                raise OSError('Video changed while extracting features')
            self._write(replace(features, file_path=str(path)), profile, sha, stat)
            return True
        except (OSError, ValueError, sqlite3.Error) as exc:
            logging.warning('Feature cache write failed: %s', exc)
            return False

    def has(self, video_path, profile=None):
        return self.get(video_path, profile=profile) is not None

    def prepare_move(self, video_path):
        """Materialize the current path before an app-controlled move."""
        return self.get(video_path)

    def clear(self):
        import shutil
        shutil.rmtree(self.cache_dir)
        self.__init__(self.cache_dir)

    def get_cache_stats(self):
        files = list(self.cache_dir.glob('*.json'))
        total_size = sum(p.stat().st_size for p in files if p.is_file())
        return {'count': len(files), 'total_size_bytes': total_size,
                'total_size_mb': round(total_size / 1024**2, 2), 'cache_dir': str(self.cache_dir)}
