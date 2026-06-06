# -*- coding: utf-8 -*-
"""
视频相似性判断 - 相似度计算模块
"""

from pathlib import Path
from typing import List, Optional
from itertools import combinations

import cv2
import numpy as np

from .config import SimilarityConfig
from .features import VideoFeatures
from .cache import FeatureCache
from .extractor import VideoFeatureExtractor
from .reporter import VideoSimilarityReporter
from tqdm import tqdm
import os
import shutil
import json
from datetime import datetime
from urllib.parse import quote


class VideoSimilarityChecker:
    """
    视频相似度计算器
    
    支持两两比较和批量查找相似视频
    """
    
    def __init__(self, config: SimilarityConfig = None, cache_dir: str = None):
        """
        初始化相似度计算器
        
        Args:
            config: 配置对象
            cache_dir: 缓存目录（如果不传则优先使用 config 配置，最后回退到默认）
        """
        self.config = config or SimilarityConfig()
        
        # 优先级: 显式参数 > config配置 > 默认
        final_cache_dir = cache_dir or self.config.cache_dir
        
        self.cache = FeatureCache(final_cache_dir)
        self.extractor = VideoFeatureExtractor(self.config, self.cache)
    
    def _compare_hashes(self, hashes_a: list, hashes_b: list) -> float:
        """
        比较两组哈希的相似度
        
        Args:
            hashes_a: 第一组哈希列表
            hashes_b: 第二组哈希列表
            
        Returns:
            相似度分数 (0-1)
        """
        if not hashes_a or not hashes_b:
            return 0.0
        
        # 取较短列表的长度
        min_len = min(len(hashes_a), len(hashes_b))
        
        # 均匀采样对齐
        indices_a = np.linspace(0, len(hashes_a) - 1, min_len, dtype=int)
        indices_b = np.linspace(0, len(hashes_b) - 1, min_len, dtype=int)
        
        similarities = []
        max_diff = self.config.hash_size ** 2  # 最大汉明距离
        
        for i, j in zip(indices_a, indices_b):
            diff = hashes_a[i] - hashes_b[j]  # 汉明距离
            sim = 1 - (diff / max_diff)
            similarities.append(sim)
        
        return float(np.mean(similarities))
    
    def _compare_histograms(self, hists_a: list, hists_b: list) -> float:
        """
        比较两组直方图的相似度
        
        Args:
            hists_a: 第一组直方图列表
            hists_b: 第二组直方图列表
            
        Returns:
            相似度分数 (0-1)
        """
        if not hists_a or not hists_b:
            return 0.0
        
        min_len = min(len(hists_a), len(hists_b))
        indices_a = np.linspace(0, len(hists_a) - 1, min_len, dtype=int)
        indices_b = np.linspace(0, len(hists_b) - 1, min_len, dtype=int)
        
        similarities = []
        for i, j in zip(indices_a, indices_b):
            # 使用相关性比较
            sim = cv2.compareHist(hists_a[i], hists_b[j], cv2.HISTCMP_CORREL)
            # 归一化到 [0, 1]
            sim = (sim + 1) / 2
            similarities.append(sim)
        
        return float(np.mean(similarities))
    
    def _calculate_similarity_score(self, features_a: VideoFeatures, features_b: VideoFeatures) -> dict:
        """
        计算两个特征对象的相似度分数（纯内存计算）
        """
        # 1. 时长相似度
        duration_diff = abs(features_a.duration - features_b.duration)
        max_duration = max(features_a.duration, features_b.duration)
        duration_sim = 1 - (duration_diff / max_duration) if max_duration > 0 else 0
        
        # 智能时长判定 (结合比例和绝对值)
        # 条件：相差 6s 内 OR 比例大于 0.85 -> 视为“值得比对”
        is_duration_acceptable = (duration_diff <= 6.0) or (duration_sim >= 0.85)

        # 硬性底线：如果时长相差超过 40% 且绝对值超过 15 秒，视为完全无关
        if not is_duration_acceptable and (duration_sim < 0.6 and duration_diff > 15):
            return {
                'similar': False,
                'score': 0.0,
                'level': '不相似',
                'reason': f'时长差异巨大 ({round(duration_diff, 1)}s)',
                'details': { 'duration_similarity': round(duration_sim, 4) }
            }

        # 记录是否超过“建议”阈值（用于等级判定）
        duration_too_different = not is_duration_acceptable
        
        # 2. 计算各特征相似度
        phash_sim = self._compare_hashes(features_a.phashes, features_b.phashes)
        dhash_sim = self._compare_hashes(features_a.dhashes, features_b.dhashes)
        hist_sim = self._compare_histograms(features_a.histograms, features_b.histograms)
        
        # 3. 加权融合
        final_score = (
            self.config.weight_duration * duration_sim +
            self.config.weight_phash * phash_sim +
            self.config.weight_dhash * dhash_sim +
            self.config.weight_histogram * hist_sim
        )
        
        # 4. 判定结果
        if final_score >= self.config.similarity_high:
            level = '高度相似' if not duration_too_different else '可能相似 (存在时长差异)'
            similar = True
        elif final_score >= self.config.similarity_medium:
            level = '可能相似'
            similar = True
        else:
            level = '不相似'
            similar = False
            
        return {
            'similar': similar,
            'score': round(final_score, 4),
            'level': level,
            'duration_warning': duration_too_different,
            'details': {
                'duration_similarity': round(duration_sim, 4),
                'phash_similarity': round(phash_sim, 4),
                'dhash_similarity': round(dhash_sim, 4),
                'histogram_similarity': round(hist_sim, 4)
            }
        }

    def compare(self, video_a: str, video_b: str, use_cache: bool = True, verbose: bool = True) -> dict:
        """
        比较两个视频的相似度
        
        Args:
            video_a: 第一个视频路径
            video_b: 第二个视频路径
            use_cache: 是否使用缓存
            verbose: 是否输出日志
            
        Returns:
            包含相似度分数 and 详细信息的字典
        """
        if verbose:
            print(f"\n比较视频相似度:")
            print(f"  视频 A: {Path(video_a).name}")
            print(f"  视频 B: {Path(video_b).name}")
        
        # 提取特征
        features_a = self.extractor.extract(video_a, use_cache, verbose)
        features_b = self.extractor.extract(video_b, use_cache, verbose)
        
        # 计算相似度
        result = self._calculate_similarity_score(features_a, features_b)
        
        # 补充视频基本信息
        result.update({
            'video_a': {
                'path': video_a,
                'name': Path(video_a).name,
                'duration': round(features_a.duration, 2),
                'resolution': features_a.resolution
            },
            'video_b': {
                'path': video_b,
                'name': Path(video_b).name,
                'duration': round(features_b.duration, 2),
                'resolution': features_b.resolution
            }
        })
        
        return result
    
    def find_similar(self, video_path: str, video_list: list, threshold: float = None) -> list:
        """
        在视频列表中查找与目标视频相似的视频
        """
        if threshold is None:
            threshold = self.config.similarity_medium
        
        results = []
        target_feat = self.extractor.extract(video_path, use_cache=True, verbose=False)
        
        for other_video in video_list:
            if Path(video_path).resolve() == Path(other_video).resolve():
                continue
            
            try:
                other_feat = self.extractor.extract(other_video, use_cache=True, verbose=False)
                comparison = self._calculate_similarity_score(target_feat, other_feat)
                if comparison['score'] >= threshold:
                    comparison.update({
                        'path': other_video,
                        'name': Path(other_video).name
                    })
                    results.append(comparison)
            except Exception as e:
                print(f"  [错误] 比较 {Path(other_video).name} 时出错: {e}")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    @staticmethod
    def _process_video_task(video_path: str, extractor_config: SimilarityConfig) -> Optional[VideoFeatures]:
        """单个视频处理任务"""
        from .extractor import VideoFeatureExtractor
        try:
            local_extractor = VideoFeatureExtractor(config=extractor_config)
            return local_extractor.extract(video_path, use_cache=True, verbose=False)
        except Exception:
            return None

    def find_all_similar_pairs(self, video_list: list, threshold: float = None, 
                                show_progress: bool = True) -> List[dict]:
        """
        在视频列表中查找所有相似的视频对 (优化版：时长窗口预过滤)
        """
        from concurrent.futures import ProcessPoolExecutor, as_completed
        import os
        
        if not video_list:
            return []
            
        if threshold is None:
            threshold = self.config.similarity_medium
            
        max_workers = self.config.max_workers
        if max_workers is None:
            max_workers = os.cpu_count() or 1
        
        # 1. 预加载所有特征
        print(f"\n[1/2] 正在加载视频特征 ({len(video_list)} 个)...")
        features_map = {}
        valid_videos = []
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = { executor.submit(self._process_video_task, v, self.config): v for v in video_list }
            iterator = as_completed(future_to_video)
            if show_progress:
                iterator = tqdm(iterator, total=len(video_list), desc="加载进度", unit="v", leave=True)
            
            for future in iterator:
                v_path = future_to_video[future]
                try:
                    feat = future.result()
                    if feat:
                        features_map[v_path] = feat
                        valid_videos.append(v_path)
                except Exception: pass
                    
        print(f"  加载完成，有效视频: {len(valid_videos)}/{len(video_list)}")
        
        # 2. 优化后的窗口比对
        # 按照时长排序
        valid_videos.sort(key=lambda v: features_map[v].duration)
        
        similar_pairs = []
        n = len(valid_videos)
        
        # 估算需要比较的对数（仅用于进度条）
        # 这里很难精确计算，我们用粗略的 combinations 作为分母，但由于窗口过滤，实际会快得多
        approx_total = n * (n - 1) // 2 
        
        print(f"\n[2/2] 正在比对特征 (窗口过滤模式)...")
        
        # 使用 tqdm 监控进度（基于 i 迭代）
        pbar = tqdm(total=approx_total, desc="比对进度", unit="pair") if show_progress else None
        
        for i in range(n):
            video_a = valid_videos[i]
            feat_a = features_map[video_a]
            dur_a = feat_a.duration
            
            # 窗口过滤：只和时长接近的视频比较
            # 根据 _calculate_similarity_score 的硬性底线 (duration_sim >= 0.6)
            # max_dur_limit = dur_a / 0.6 (假设 A 是较短的)
            for j in range(i + 1, n):
                video_b = valid_videos[j]
                feat_b = features_map[video_b]
                dur_b = feat_b.duration
                
                # 如果 B 超过 A 的时长太多，后续排过序的视频都没必要比了，跳出内层循环
                # 这里根据：abs(diff)/max < 0.4 -> (dur_b - dur_a) / dur_b < 0.4 -> dur_b * 0.6 < dur_a -> dur_b < dur_a / 0.6
                if dur_b > (dur_a / 0.6) and (dur_b - dur_a > 15):
                    # 同时也要考虑绝对值宽容度，如果不满足绝对值宽容且比例也超了，就断开
                    if dur_b - dur_a > 15: # 绝对值底线
                        if pbar: pbar.update(n - j) # 更新跳过的进度
                        break
                
                # 执行精细比对
                result = self._calculate_similarity_score(feat_a, feat_b)
                if result['score'] >= threshold:
                    result.update({
                        'video_a': { 'path': video_a, 'name': Path(video_a).name, 'duration': round(dur_a, 2), 'resolution': feat_a.resolution },
                        'video_b': { 'path': video_b, 'name': Path(video_b).name, 'duration': round(dur_b, 2), 'resolution': feat_b.resolution }
                    })
                    similar_pairs.append(result)
                
                if pbar: pbar.update(1)

        if pbar: pbar.close()
        similar_pairs.sort(key=lambda x: x['score'], reverse=True)
        return similar_pairs
    
    @staticmethod
    def _process_video_task_no_cache(video_path: str, extractor_config: SimilarityConfig) -> Optional[VideoFeatures]:
        """
        单个视频处理任务（不使用缓存，用于新增视频）
        """
        from .extractor import VideoFeatureExtractor
        try:
            local_extractor = VideoFeatureExtractor(config=extractor_config)
            return local_extractor.extract(video_path, use_cache=False, verbose=False)
        except Exception:
            return None
    
    def find_incremental_similar_pairs(
        self, 
        new_videos: List[str], 
        existing_videos: List[str], 
        threshold: float = None,
        show_progress: bool = True
    ) -> List[dict]:
        """
        增量比对：仅将新视频与已有视频进行比对
        
        Args:
            new_videos: 新增视频路径列表（不缓存特征）
            existing_videos: 已有视频路径列表（使用缓存）
            threshold: 相似度阈值
            show_progress: 是否显示进度
            
        Returns:
            相似视频对列表，按相似度降序排列
        """
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from itertools import product
        import os
        
        if not new_videos or not existing_videos:
            return []
            
        if threshold is None:
            threshold = self.config.similarity_medium
            
        max_workers = self.config.max_workers
        if max_workers is None:
            max_workers = os.cpu_count() or 1
        
        # 1. 加载已有库的视频特征（使用缓存）
        print(f"\n[1/3] 正在加载已有库视频特征 ({len(existing_videos)} 个)...")
        print(f"  并行模式: {max_workers} 进程 | 使用缓存: 是")
        
        existing_features_map = {}
        valid_existing = []
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(self._process_video_task, video, self.config): video 
                for video in existing_videos
            }
            
            iterator = as_completed(future_to_video)
            if show_progress:
                iterator = tqdm(iterator, total=len(existing_videos), desc="已有库", unit="v", leave=True)
            
            for future in iterator:
                video_path = future_to_video[future]
                try:
                    features = future.result()
                    if features:
                        existing_features_map[video_path] = features
                        valid_existing.append(video_path)
                except Exception as e:
                    if show_progress:
                        iterator.write(f"  [Error] {Path(video_path).name}: {e}")
                    else:
                        print(f"  [Error] {Path(video_path).name}: {e}")
        
        print(f"  已有库加载完成: {len(valid_existing)}/{len(existing_videos)}")
        
        # 2. 加载新增视频特征（不使用缓存）
        print(f"\n[2/3] 正在提取新增视频特征 ({len(new_videos)} 个)...")
        print(f"  并行模式: {max_workers} 进程 | 使用缓存: 否")
        
        new_features_map = {}
        valid_new = []
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(self._process_video_task_no_cache, video, self.config): video 
                for video in new_videos
            }
            
            iterator = as_completed(future_to_video)
            if show_progress:
                iterator = tqdm(iterator, total=len(new_videos), desc="新增视频", unit="v", leave=True)
            
            for future in iterator:
                video_path = future_to_video[future]
                try:
                    features = future.result()
                    if features:
                        new_features_map[video_path] = features
                        valid_new.append(video_path)
                except Exception as e:
                    if show_progress:
                        iterator.write(f"  [Error] {Path(video_path).name}: {e}")
                    else:
                        print(f"  [Error] {Path(video_path).name}: {e}")
        
        print(f"  新增视频加载完成: {len(valid_new)}/{len(new_videos)}")
        
        # 3. 笛卡尔积比对（新视频 × 已有库）
        similar_pairs = []
        total_pairs = len(valid_new) * len(valid_existing)
        print(f"\n[3/3] 正在比对特征 (共 {total_pairs} 对)...")
        
        pair_iterator = product(valid_new, valid_existing)
        if show_progress and total_pairs > 0:
            pair_iterator = tqdm(pair_iterator, total=total_pairs, desc="比对进度", unit="pair", leave=True)
        
        for new_video, existing_video in pair_iterator:
            try:
                feat_new = new_features_map[new_video]
                feat_existing = existing_features_map[existing_video]
                
                result = self._calculate_similarity_score(feat_new, feat_existing)
                
                if result['score'] >= threshold:
                    result.update({
                        'video_a': {
                            'path': new_video,
                            'name': Path(new_video).name,
                            'duration': round(feat_new.duration, 2),
                            'resolution': feat_new.resolution
                        },
                        'video_b': {
                            'path': existing_video,
                            'name': Path(existing_video).name,
                            'duration': round(feat_existing.duration, 2),
                            'resolution': feat_existing.resolution
                        }
                    })
                    similar_pairs.append(result)
                    
            except Exception:
                pass
        
        similar_pairs.sort(key=lambda x: x['score'], reverse=True)
        
        return similar_pairs
    
    def collect_videos_from_directories(self, directories: List[str]) -> List[str]:
        """
        从多个目录收集视频文件
        
        Args:
            directories: 目录路径列表
            
        Returns:
            视频文件路径列表
        """
        video_files = []
        extensions = self.config.video_extensions
        
        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                print(f"  [警告] 目录不存在: {directory}")
                continue
            
            if not dir_path.is_dir():
                print(f"  [警告] 路径不是目录: {directory}")
                continue
            
            # 递归查找视频文件
            for ext in extensions:
                video_files.extend([str(f) for f in dir_path.rglob(f'*{ext}')])
                video_files.extend([str(f) for f in dir_path.rglob(f'*{ext.upper()}')])
        
        # 去重
        video_files = list(set(video_files))
        
        return video_files
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_cache_stats()
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()

    def generate_report(self, similar_pairs: List[dict], base_output_dir: str = "output/video_similarity"):
        """
        生成相似视频报告
        
        Args:
            similar_pairs: 相似视频对列表
            base_output_dir: 基础输出目录
        """
        VideoSimilarityReporter.generate_report(similar_pairs, base_output_dir)

    # 已移至 VideoSimilarityReporter


