"""Exercise migration failures/resumption with disposable files and real caches."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import imagehash
import numpy as np

from scripts.regroup_library import (apply_plan, make_plan, read_json, write_json,
                                     group_index, NAMES, path_key, remap_records)
from utils.video_similarity.cache import FeatureCache
from utils.video_similarity.features import VideoFeatures


class RegroupTests(unittest.TestCase):
    def test_boundaries_match_application_kib_rounding(self):
        self.assertEqual(group_index(0), 0)
        self.assertEqual(group_index(2 * 1024**2 - 1024), 0)
        self.assertEqual(group_index(2 * 1024**2 - 1), 1)
        self.assertEqual(group_index(32 * 1024**2), 7)

    def test_report_and_ignored_pair_ids_follow_renames(self):
        a, b, c = map(lambda p: str(Path(p).resolve()), ['a.mp4', 'b.mp4', 'c.mp4'])
        report, dismissed = remap_records([{'videos': [{'originalPath': a}]}],
            {'version': 1, 'dismissed': {'old': {'paths': [a, b], 'dismissed_at': 'keep'}}}, {path_key(a): c})
        self.assertEqual(report[0]['videos'][0]['originalPath'], c)
        key = hashlib.sha256('|'.join(sorted([b, c])).encode()).hexdigest()[:16]
        self.assertEqual(dismissed['dismissed'][key]['dismissed_at'], 'keep')

    def test_interrupt_after_rename_resumes_without_decode_or_lost_collision(self):
        with tempfile.TemporaryDirectory(prefix='regroup-test-') as tmp:
            root = Path(tmp)
            archive, download = root / 'videos', root / 'downloads'
            download.mkdir()
            cache = FeatureCache(root / 'cache')
            profile = {'algorithm': 1, 'num_sample_frames': 3, 'hash_size': 8, 'hist_bins': 4}
            original_contents = []
            for i, name in enumerate(['old-a', 'old-b']):
                folder = archive / name
                folder.mkdir(parents=True)
                source = folder / 'same.mp4'
                source.write_bytes(bytes([i + 1]) * 1000)
                original_contents.append(source.read_bytes())
                h = imagehash.ImageHash(np.zeros((8, 8), dtype=bool))
                feature = VideoFeatures(str(source), cache.get_file_hash(source), 1., 3, 3., 16, 16,
                                        [h]*3, [h]*3, [np.zeros(8)]*3, [0., 1/3, 2/3])
                self.assertTrue(cache.set(feature, profile))
            cfg = {'archive_base_dir': str(archive), 'download_dir': str(download),
                   'cache_dir': str(root / 'cache'), 'output_dir': str(root / 'report'),
                   'categories': {name: {'archive_subdir': name, 'size_range_kb': [0, None]}
                                  for name in ['old-a', 'old-b']},
                   'video_extensions': ['.mp4'], 'similarity': profile}
            config_path = root / 'config.json'
            write_json(config_path, cfg)
            run_dir = root / 'migration'
            plan = make_plan(config_path, run_dir)
            self.assertEqual(plan['renamed_collisions'], 1)
            original_get = FeatureCache.get
            def interrupt_moved(instance, path, *args):
                if Path(path).parent.name in NAMES:
                    raise RuntimeError('Simulated power interruption after rename')
                return original_get(instance, path, *args)
            with patch.object(FeatureCache, 'get', interrupt_moved):
                with self.assertRaisesRegex(RuntimeError, 'interruption'):
                    apply_plan(plan, run_dir)
            self.assertEqual(read_json(config_path), cfg)
            with patch('cv2.VideoCapture', side_effect=AssertionError('Must never decode')):
                result = apply_plan(plan, run_dir)
                again = apply_plan(plan, run_dir)
            self.assertEqual(result['features_reused'], 2)
            self.assertTrue(again['success'])
            self.assertEqual([Path(e['target']).read_bytes() for e in plan['entries']], original_contents)
            self.assertEqual(len(list(cache.cache_dir.glob('*.json'))), 2)
            self.assertEqual(len(read_json(config_path)['categories']), 8)


if __name__ == '__main__':
    unittest.main()
