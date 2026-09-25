"""Integration checks use generated videos and an isolated configuration only."""

from functools import partial
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote

import cv2
import numpy as np

from utils.video_similarity.server import SimilarityReportHandler as Handler
from utils.video_similarity.tasks import TaskBusy, TaskManager
from utils.video_similarity.reporter import VideoSimilarityReporter


def make_video(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 12, (96, 64))
    if not writer.isOpened():
        raise RuntimeError('Fixture video encoder unavailable')
    for index in range(24):
        frame = np.zeros((64, 96, 3), dtype=np.uint8)
        frame[:] = (50, 80, 100)
        cv2.rectangle(frame, (index, 12), (index + 25, 40), (190, 150, 40), -1)
        writer.write(frame)
    writer.release()


class TaskTests(unittest.TestCase):
    def test_clear_history_persistence_and_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            path.write_text(json.dumps([{'id': 'old', 'state': 'complete'}]), encoding='utf-8')
            manager = TaskManager(path)
            with patch.object(manager, '_save', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    manager.clear_history()
            self.assertIsNotNone(manager.snapshot('old'))
            self.assertEqual(manager.clear_history(), 1)
            self.assertEqual(TaskManager(path).snapshot()['tasks'], [])

    def test_serialization_persistence_and_interrupted_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            manager = TaskManager(path)
            entered, release = threading.Event(), threading.Event()
            def operation(progress):
                progress('testing', 1, 2, 'one file processed')
                entered.set()
                release.wait(5)
                return {'success': False, 'errors': [{'error': 'fixture failure'}]}
            task = manager.start('fixture', 'Fixture', operation)
            entered.wait(2)
            try:
                with self.assertRaises(TaskBusy):
                    manager.start('second', 'Second', lambda p: {})
                with self.assertRaises(TaskBusy):
                    with manager.exclusive():
                        pass
                self.assertEqual(manager.snapshot(task['id'])['completed'], 1)
            finally:
                release.set()
            for _ in range(100):
                if manager.snapshot()['active_id'] is None:
                    break
                time.sleep(.02)
            restored = TaskManager(path)
            self.assertEqual(restored.snapshot(task['id'])['state'], 'partial')
            rows = json.loads(path.read_text(encoding='utf-8'))
            rows[0]['state'] = 'running'
            path.write_text(json.dumps(rows), encoding='utf-8')
            interrupted = TaskManager(path)
            self.assertEqual(interrupted.snapshot(task['id'])['state'], 'interrupted')
            self.assertIsNone(interrupted.snapshot()['active_id'])


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='video-workspace-test-')
        self.root = Path(self.temp.name)
        self.download = self.root / 'downloads'
        self.archive = self.root / 'archive'
        self.output = self.root / 'output'
        self.download.mkdir()
        (self.archive / 'small').mkdir(parents=True)
        self.output.mkdir()
        self.config = dict(download_dir=str(self.download), archive_base_dir=str(self.archive),
                           cache_dir=str(self.root / 'cache'), output_dir=str(self.output),
                           log_dir=str(self.root / 'logs'), video_extensions=['.avi', '.mp4'],
                           categories={'XS': {'size_range_kb': [0, None], 'archive_subdir': 'small'}},
                           similarity={'max_workers': 1, 'num_sample_frames': 3})
        config_file = self.root / 'config.json'
        config_file.write_text(json.dumps(self.config), encoding='utf-8')
        self.environment = patch.dict(os.environ, {'VIDEO_PROCESSOR_CONFIG': str(config_file)})
        self.environment.start()
        (self.output / 'data.json').write_text('[]', encoding='utf-8')
        VideoSimilarityReporter.generate_html_report([], self.output)
        Handler._reload_session_from_disk(self.output)
        Handler._SERVER_OUTPUT_DIR = self.output
        Handler._TASKS = TaskManager(self.output / 'tasks.json')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(self.output)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.environment.stop()
        self.temp.cleanup()

    def request(self, route, body=None, origin=None):
        request = Request(self.url + route, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json', **({'Origin': origin} if origin else {})})
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def run_task(self, route, body=None):
        status, data = self.request(route, body or {})
        self.assertEqual(status, 202, data)
        task_id = data['task']['id']
        for _ in range(600):
            _, data = self.request('/api/tasks/' + task_id)
            if data['task']['state'] != 'running':
                return data['task']
            time.sleep(.1)
        self.fail('Task did not finish within 60 seconds')

    def test_classify_rename_migrate_with_real_fixture_video(self):
        make_video(self.download / 'new video.avi')
        task = self.run_task('/api/download-library/classify')
        self.assertEqual(task['state'], 'complete', task)
        self.assertEqual(task['result']['moved_count'], 1)
        classified = list((self.download / 'XS').glob('*.avi'))
        self.assertEqual(len(classified), 1)
        self.assertRegex(classified[0].stem, r'^\d{17}$')
        rename = self.run_task('/api/download-library/rename')
        self.assertEqual(rename['result']['renamed_count'], 0)
        migration = self.run_task('/api/download-library/migrate')
        self.assertEqual(migration['state'], 'complete', migration)
        self.assertEqual(migration['result']['cached_count'], 1)
        self.assertFalse(classified[0].exists())
        self.assertEqual(len(list((self.archive / 'small').glob('*.avi'))), 1)
        _, status = self.request('/api/download-library/status')
        self.assertEqual(status['totals']['archive_count'], 1)
        self.assertEqual(status['totals']['classified_count'], 0)

    def test_incremental_classify_scan_and_dismiss(self):
        make_video(self.download / 'new.avi')
        make_video(self.archive / 'small' / 'existing.avi')
        task = self.run_task('/api/similarity/refresh', {'mode': 'incremental_downloads', 'classify_first': True})
        self.assertEqual(task['state'], 'complete', task)
        self.assertEqual(task['result']['active_count'], 1, task)
        _, pair = self.request('/api/pair?index=0')
        videos = pair['pair']['videos']
        body = {'pathA': videos[0]['originalPath'], 'pathB': videos[1]['originalPath']}
        with patch.object(Handler, '_save_dismissed_pair', side_effect=OSError('fixture disk error')):
            status, failure = self.request('/api/dismiss', body)
            self.assertEqual(status, 500)
            self.assertFalse(failure['success'])
            self.assertEqual(self.request('/api/metadata')[1]['total'], 1)
        _, result = self.request('/api/dismiss', body)
        self.assertTrue(result['success'])
        self.assertEqual(result['total'], 0)
        self.assertTrue(all(Path(video['originalPath']).exists() for video in videos))
        Handler._reload_session_from_disk(self.output)
        self.assertEqual(self.request('/api/metadata')[1]['total'], 0)

    def test_prune_failure_does_not_claim_success_or_remove_group(self):
        a, b = self.download / 'a.mp4', self.download / 'b.mp4'
        a.write_bytes(b'fixture'); b.write_bytes(b'fixture')
        pair = {'videos': [{'originalPath': str(a)}, {'originalPath': str(b)}]}
        (self.output / 'data.json').write_text(json.dumps([pair]), encoding='utf-8')
        Handler._reload_session_from_disk(self.output)
        with patch('utils.video_similarity.server.recycle_file', side_effect=OSError('file is busy')):
            _, result = self.request('/api/prune', {'files': [str(a)]})
            self.assertFalse(result['success'])
            self.assertEqual(result['deleted_count'], 0)
            self.assertTrue(a.exists())
            self.assertEqual(self.request('/api/metadata')[1]['total'], 1)
        trash = self.root / 'test-trash.mp4'
        with patch('utils.video_similarity.server.recycle_file', side_effect=lambda path: path.rename(trash)):
            _, result = self.request('/api/prune', {'files': [str(a)]})
            self.assertTrue(result['success'])
            self.assertEqual(result['total'], 0)
            self.assertTrue(trash.exists())

    def test_concurrent_writes_and_cross_origin_requests_are_rejected(self):
        release = threading.Event()
        def blocked_operation(handler, progress):
            release.wait(5)
            return {'success': True}
        with patch.object(Handler, 'classify_downloads', blocked_operation):
            status, data = self.request('/api/download-library/classify', {})
            self.assertEqual(status, 202)
            try:
                self.assertEqual(self.request('/api/download-library/migrate', {})[0], 409)
                self.assertEqual(self.request('/api/dismiss', {})[0], 409)
                self.assertEqual(self.request('/api/tasks/clear', {})[0], 409)
                self.assertEqual(self.request('/api/cache/orphans/status')[0], 409)
                self.assertEqual(self.request('/api/cache/orphans', {}, origin='https://example.com')[0], 403)
                self.assertEqual(self.request('/api/tasks')[0], 200)
            finally:
                release.set()
            for _ in range(100):
                if Handler._TASKS.snapshot()['active_id'] is None:
                    break
                time.sleep(.02)

    def test_history_clear_does_not_change_files_or_review_state(self):
        path = self.download / 'a.mp4'
        path.write_bytes(b'video fixture')
        report = (self.output / 'data.json').read_bytes()
        task = self.run_task('/api/cache/orphans', {'dry_run': True})
        self.assertEqual(self.request('/api/tasks/clear', {}, origin='https://example.com')[0], 403)
        status, result = self.request('/api/tasks/clear', {})
        self.assertEqual(status, 200)
        self.assertEqual(result['cleared_count'], 1)
        self.assertEqual(self.request('/api/tasks')[1]['tasks'], [])
        self.assertEqual(self.request('/api/tasks/' + task['id'])[0], 404)
        self.assertEqual(TaskManager(self.output / 'tasks.json').snapshot()['tasks'], [])
        self.assertEqual(path.read_bytes(), b'video fixture')
        self.assertEqual((self.output / 'data.json').read_bytes(), report)

    def test_orphan_status_is_read_only_and_updates_after_cleanup(self):
        cache_dir = Path(self.config['cache_dir'])
        cache_dir.mkdir()
        orphan = cache_dir / 'orphan.json'
        orphan.write_bytes(b'{}')
        status, result = self.request('/api/cache/orphans/status')
        self.assertEqual(status, 200)
        self.assertEqual((result['count'], result['bytes']), (1, 2))
        self.assertTrue(orphan.exists())
        self.assertEqual(self.request('/api/tasks')[1]['tasks'], [])
        self.run_task('/api/cache/orphans', {'dry_run': False})
        result = self.request('/api/cache/orphans/status')[1]
        self.assertEqual((result['count'], result['bytes']), (0, 0))

    def test_missing_cache_repair_and_preview_do_not_move_video(self):
        path = self.archive / 'small' / 'existing.avi'
        make_video(path)
        task = self.run_task('/api/cache/repair')
        self.assertEqual(task['state'], 'complete', task)
        self.assertEqual(task['result']['cached_count'], 1)
        from utils.video_similarity.cache import FeatureCache
        self.assertTrue(FeatureCache(self.config['cache_dir']).has(str(path)))
        preview = self.run_task('/api/cache/orphans', {'dry_run': True})
        self.assertEqual(preview['state'], 'complete', preview)
        self.assertTrue(preview['result']['dry_run'])
        self.assertTrue(path.exists())

    def test_rebuild_and_migrate_reuse_features_without_decoding(self):
        from utils.video_similarity.cache import FeatureCache
        from utils.video_similarity.extractor import VideoFeatureExtractor
        source = self.download / 'XS' / '20260101000000000.avi'
        make_video(source)
        cache = FeatureCache(self.config['cache_dir'])
        original = VideoFeatureExtractor(cache=cache).extract(str(source))
        target = source.with_name('20260102000000000.avi')
        source.rename(target)
        with patch('cv2.VideoCapture', side_effect=AssertionError('Reuse must not decode')):
            rebuilt = self.run_task('/api/cache/rebuild')
            self.assertEqual(rebuilt['state'], 'complete', rebuilt)
            self.assertEqual(rebuilt['result']['rebuilt_count'], 1)
            self.assertEqual(rebuilt['result']['missing_count'], 0)
            task = self.run_task('/api/download-library/migrate')
            self.assertEqual(task['state'], 'complete', task)
            self.assertEqual(task['result']['cached_count'], 1)
        archived = list((self.archive / 'small').glob('*.avi'))[0]
        self.assertEqual(cache.get(str(archived)).file_hash, original.file_hash)

    def test_migration_reports_cache_write_failure_without_losing_video(self):
        path = self.download / 'XS' / '20260101000000000.avi'
        make_video(path)
        with patch('utils.video_similarity.cache.FeatureCache.set', return_value=None):
            task = self.run_task('/api/download-library/migrate')
        self.assertEqual(task['state'], 'partial', task)
        self.assertEqual(task['result']['migrated_count'], 1)
        self.assertEqual(task['result']['cached_count'], 0)
        self.assertEqual(task['result']['errors'][0]['stage'], 'cache')
        self.assertTrue((self.archive / 'small' / path.name).exists())

    def test_video_range_requests_are_bounded(self):
        path = self.download / 'range.mp4'
        path.write_bytes(b'0123456789')
        url = self.url + '/stream/' + quote(str(path))
        for requested, expected in [('bytes=5-9999', b'56789'), ('bytes=-3', b'789')]:
            with urlopen(Request(url, headers={'Range': requested}), timeout=5) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), expected)
                self.assertEqual(int(response.headers['Content-Length']), len(expected))
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(url, headers={'Range': 'bytes=99-'}), timeout=5)
        self.assertEqual(caught.exception.code, 416)


if __name__ == '__main__':
    unittest.main()
