"""Reuse existing feature JSONs; never decode, move, or delete videos."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.video_similarity.cache import FeatureCache
from utils.video_similarity.config import SimilarityConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir')
    parser.add_argument('--full-hash', action='store_true', help='Recheck complete contents even when file identity is unchanged')
    args = parser.parse_args()
    cache = FeatureCache(args.cache_dir or SimilarityConfig().cache_dir)
    start = time.perf_counter()
    last = [start]
    def progress(done, total):
        now = time.perf_counter()
        if now - last[0] >= 5 or done == total:
            print(f'Indexed {done}/{total}, elapsed {now-start:.1f}s', flush=True)
            last[0] = now
    result = cache.rebuild_index(full_hash=args.full_hash, progress=progress)
    result['seconds'] = round(time.perf_counter() - start, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
