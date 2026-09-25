from pathlib import Path
import tempfile
import unittest

from utils.video_similarity.reporter import VideoSimilarityReporter
from utils.video_similarity.server import SimilarityReportHandler


class ReportMetricsTests(unittest.TestCase):
    def test_report_preserves_precise_parameters_and_computed_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'sample.mp4'
            video.write_bytes(b'fixture')
            info = {'path': str(video), 'name': video.name, 'duration': 3.67, 'resolution': '960x540'}
            components = {'duration_similarity': .9, 'phash_similarity': .87}
            row = VideoSimilarityReporter._prepare_data([{'video_a': info, 'video_b': info,
                                                         'score': .93, 'details': components}])[0]
            self.assertEqual(row['scoreDetails'], components)
            self.assertEqual(row['videos'][0]['durationSeconds'], 3.67)
            self.assertEqual(row['videos'][0]['sizeBytes'], 7)
            self.assertEqual(row['recommend'], 'equal')

    def test_log_bins_cover_zero_and_use_binary_units(self):
        bucket = SimilarityReportHandler._log_size_bucket
        self.assertEqual(bucket(0), bucket(1024))
        self.assertEqual(bucket(0)['label'], '<1 MiB')
        self.assertEqual(bucket(2*1024**2)['label'], '2-4 MiB')
        self.assertEqual(bucket(1024**3)['label'], '1-2 GiB')
