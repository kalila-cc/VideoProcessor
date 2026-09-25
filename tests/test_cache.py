"""Cache recovery and invalidation, using disposable files only."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from unittest.mock import patch

import imagehash
import numpy as np

from utils.video_similarity.cache import FeatureCache
from utils.video_similarity.features import VideoFeatures, sample_frame_positions
from utils.video_similarity.extractor import VideoFeatureExtractor
from utils.video_similarity.config import SimilarityConfig
from utils.video_similarity.janitor import CacheJanitor


def write_in_process(args):
    directory, feature, profile = args
    return FeatureCache(directory).set(VideoFeatures.from_dict(feature), profile)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='video-cache-test-')
        self.root = Path(self.temp.name)
        self.cache = FeatureCache(self.root / 'cache')
        self.source = self.root / 'source.bin'
        self.source.write_bytes(b'A' * 65536 + b'B' * 65536 + b'C' * 65536)
        self.profile = dict(algorithm=1, num_sample_frames=3, hash_size=8, hist_bins=4)
        h = imagehash.ImageHash(np.zeros((8, 8), dtype=bool))
        self.feature = VideoFeatures(str(self.source), self.cache.get_file_hash(self.source),
                                     10., 100, 10., 16, 16, [h]*3, [h]*3,
                                     [np.zeros(8)]*3, [p/100 for p in sample_frame_positions(100, 3)])

    def tearDown(self):
        self.temp.cleanup()

    def current_record(self):
        self.assertTrue(self.cache.set(self.feature, self.profile))
        return self.cache.cache_dir / (self.cache._get_cache_id(self.source) + '.json')

    def test_current_index_then_rename_reuses_without_decode_or_full_read(self):
        record = self.current_record()
        original = record.read_bytes()
        result = self.cache.rebuild_index()
        self.assertEqual(result['indexed'], 1)
        self.assertEqual(record.read_bytes(), original)
        target = self.root / 'renamed.bin'
        self.source.rename(target)
        config = SimilarityConfig()
        config.num_sample_frames = 3; config.hash_size = 8; config.hist_bins = 4
        extractor = VideoFeatureExtractor(config, self.cache)
        with patch('cv2.VideoCapture', side_effect=AssertionError('Must not decode')):
            with patch.object(self.cache, '_sha256', side_effect=AssertionError('Same inode requires no full read')):
                feat = extractor.extract(str(target))
        self.assertEqual(feat.file_path, str(target))
        self.assertEqual(feat.file_hash, self.feature.file_hash)
        self.assertEqual([str(h) for h in feat.phashes], [str(h) for h in self.feature.phashes])
        self.assertTrue(self.cache.has(str(target)))

    def test_copy_reuses_when_original_is_gone_and_digest_was_prepared(self):
        self.current_record()
        self.assertEqual(self.cache.rebuild_index(full_hash=True)['indexed'], 1)
        target = self.root / 'copied.bin'
        shutil.copy2(self.source, target)
        self.source.unlink()
        self.assertNotEqual(str(target.stat().st_ino), self.cache._row(self.cache._get_cache_id(self.source))['inode'])
        with patch('cv2.VideoCapture', side_effect=AssertionError('Must not decode')):
            result = FeatureCache(self.cache.cache_dir).get(str(target), self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.file_path, str(target))

    def test_same_head_tail_different_middle_never_reuses(self):
        self.cache.set(self.feature, self.profile)
        target = self.root / 'other.bin'
        target.write_bytes(b'A'*65536 + b'Z'*65536 + b'C'*65536)
        self.assertEqual(self.cache.get_file_hash(target), self.feature.file_hash)
        self.assertIsNone(self.cache.get(str(target), self.profile))

    def test_middle_changed_in_place_invalidates_even_when_quick_hash_matches(self):
        self.cache.set(self.feature, self.profile)
        old_stat = self.source.stat()
        with self.source.open('r+b') as stream:
            stream.seek(70000); stream.write(b'Z')
        os.utime(self.source, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))
        self.assertEqual(self.cache.get_file_hash(self.source), self.feature.file_hash)
        self.assertIsNone(self.cache.get(str(self.source), self.profile))

    def test_changed_extraction_parameters_do_not_reuse(self):
        self.current_record()
        self.assertIsNotNone(self.cache.get(str(self.source), self.profile))
        self.assertIsNone(self.cache.get(str(self.source), {**self.profile, 'num_sample_frames': 5}))
        self.cache.set(self.feature, self.profile)
        self.assertIsNone(self.cache.get(str(self.source), {**self.profile, 'hash_size': 16}))

    def test_orphan_cleanup_preserves_cache_for_moved_video_and_database(self):
        record = self.current_record()
        self.cache.rebuild_index()
        target = self.root / 'renamed.bin'; self.source.rename(target)
        janitor = CacheJanitor(cache=self.cache)
        preview = janitor.clean_orphans([str(target)], dry_run=True)
        self.assertEqual(preview['deleted_count'], 0)
        self.assertTrue(record.exists())
        self.assertFalse((self.cache.cache_dir / (self.cache._get_cache_id(target)+'.json')).exists())
        real = janitor.clean_orphans([str(target)], dry_run=False)
        self.assertEqual(real['deleted_count'], 0)
        self.assertTrue(self.cache.index_path.exists())
        self.assertIsNotNone(self.cache.get(str(target)))

    def test_orphan_check_skips_feature_reads_when_no_candidates(self):
        self.current_record()
        with patch.object(self.cache, '_lookup', side_effect=AssertionError('Unnecessary feature read')):
            result = CacheJanitor(cache=self.cache).clean_orphans([str(self.source)])
        self.assertEqual(result['deleted_count'], 0)

    def test_orphan_candidate_filter_preserves_reuse_and_skips_other_sizes(self):
        record = self.current_record()
        target = self.root / 'renamed.bin'
        self.source.rename(target)
        unrelated = self.root / 'unrelated.bin'
        unrelated.write_bytes(b'other size')
        with patch.object(self.cache, '_lookup', wraps=self.cache._lookup) as lookup:
            result = CacheJanitor(cache=self.cache).clean_orphans([str(target), str(unrelated)])
        self.assertEqual(result['deleted_count'], 0)
        self.assertEqual([call.args[0] for call in lookup.call_args_list], [str(target)])
        self.assertTrue(record.exists())

    def test_unversioned_or_incomplete_records_are_rejected(self):
        path = self.current_record()
        current = json.loads(path.read_text(encoding='utf-8'))
        for key in ['_cache_version', '_cache_profile', '_content_sha256']:
            incomplete = {k:v for k,v in current.items() if k != key}
            path.write_text(json.dumps(incomplete), encoding='utf-8')
            self.assertIsNone(self.cache.get(self.source))
            self.assertEqual(self.cache.rebuild_index()['indexed'], 0)
        current['_cache_version'] = 999
        path.write_text(json.dumps(current), encoding='utf-8')
        self.assertIsNone(self.cache.get(self.source))

    def test_rebuild_missing_index_uses_embedded_digest(self):
        self.current_record()
        with self.cache._db() as db:
            db.execute('DELETE FROM entries')
        self.assertEqual(self.cache.rebuild_index()['indexed'], 1)
        with self.source.open('r+b') as stream:
            stream.seek(70000); stream.write(b'Z')
        with self.cache._db() as db:
            db.execute('DELETE FROM entries')
        self.assertEqual(self.cache.rebuild_index()['indexed'], 0)
        self.assertIsNone(self.cache.get(self.source))

    def test_simultaneous_writes_are_atomic(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: FeatureCache(self.cache.cache_dir).set(self.feature, self.profile), range(12)))
        self.assertTrue(all(results))
        self.assertIsNotNone(self.cache.get(str(self.source), self.profile))
        self.assertFalse(list(self.cache.cache_dir.glob('*.tmp')))

    def test_prepare_current_before_copy_delete_preserves_features(self):
        self.current_record()
        self.cache.prepare_move(str(self.source))
        target = self.root / 'moved.bin'
        shutil.copy2(self.source, target)
        self.source.unlink()
        self.assertIsNotNone(FeatureCache(self.cache.cache_dir).get(str(target), self.profile))

    def test_multiple_processes_share_index_without_losing_cache(self):
        args = (str(self.cache.cache_dir), self.feature.to_dict(), self.profile)
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(write_in_process, [args] * 8))
        self.assertTrue(all(results))
        self.assertIsNotNone(self.cache.get(str(self.source), self.profile))

    def test_corrupt_cache_and_interrupted_temp_do_not_break_indexing(self):
        self.current_record()
        (self.cache.cache_dir / 'invalid.json').write_text('{broken', encoding='utf-8')
        (self.cache.cache_dir / 'leftover.tmp').write_text('interrupted', encoding='utf-8')
        result = self.cache.rebuild_index(full_hash=True)
        self.assertEqual(result['indexed'], 1)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['errors'], [])
        self.assertIsNotNone(self.cache.get(str(self.source)))


if __name__ == '__main__':
    unittest.main()
