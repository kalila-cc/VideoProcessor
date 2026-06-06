# -*- coding: utf-8 -*-
"""
视频相似性判断 - 特征提取模块
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import imagehash

from .config import SimilarityConfig
from .features import VideoFeatures
from .cache import FeatureCache


class VideoFeatureExtractor:
    """
    视频特征提取器
    
    采用智能采样策略提取视频关键帧，并计算多维特征：
    - 感知哈希 (pHash)
    - 差异哈希 (dHash)  
    - 颜色直方图
    """
    
    def __init__(self, config: SimilarityConfig = None, cache: FeatureCache = None):
        """
        初始化特征提取器
        
        Args:
            config: 配置对象
            cache: 缓存管理器
        """
        self.config = config or SimilarityConfig()
        
        if cache is None:
            # 如果未提供 cache 对象，则使用 config 中的路径新建一个
            self.cache = FeatureCache(self.config.cache_dir)
        else:
            self.cache = cache
    
    def _get_sample_positions(self, total_frames: int) -> list:
        """
        计算采样帧的位置
        
        策略：
        - 首帧、尾帧、中点帧（锚点）
        - 其余帧均匀分布
        
        Args:
            total_frames: 视频总帧数
            
        Returns:
            采样帧位置列表
        """
        if total_frames <= self.config.num_sample_frames:
            return list(range(total_frames))
        
        positions = set()
        
        # 添加锚点帧：首帧、尾帧、中点帧
        positions.add(0)
        positions.add(total_frames - 1)
        positions.add(total_frames // 2)
        
        # 均匀分布其余帧
        remaining = self.config.num_sample_frames - 3
        if remaining > 0:
            step = total_frames / (remaining + 1)
            for i in range(1, remaining + 1):
                pos = int(i * step)
                positions.add(min(pos, total_frames - 1))
        
        return sorted(positions)
    
    def _compute_histogram(self, frame: np.ndarray) -> np.ndarray:
        """
        计算颜色直方图
        
        使用 HSV 色彩空间，对光照变化更鲁棒
        
        Args:
            frame: BGR 格式的帧图像
            
        Returns:
            归一化的直方图数组
        """
        # 转换到 HSV 空间
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 计算 H 和 S 通道的直方图
        hist_h = cv2.calcHist([hsv], [0], None, [self.config.hist_bins], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [self.config.hist_bins], [0, 256])
        
        # 归一化并合并
        cv2.normalize(hist_h, hist_h)
        cv2.normalize(hist_s, hist_s)
        
        return np.concatenate([hist_h.flatten(), hist_s.flatten()])
    
    def _compute_frame_hashes(self, frame: np.ndarray) -> tuple:
        """
        计算帧的感知哈希和差异哈希
        
        Args:
            frame: BGR 格式的帧图像
            
        Returns:
            (phash, dhash) 元组
        """
        # 转换为 PIL Image
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        
        # 计算哈希
        phash = imagehash.phash(pil_image, hash_size=self.config.hash_size)
        dhash = imagehash.dhash(pil_image, hash_size=self.config.hash_size)
        
        return phash, dhash
    
    def extract(self, video_path: str, use_cache: bool = True, verbose: bool = False) -> VideoFeatures:
        """
        提取视频特征
        
        Args:
            video_path: 视频文件路径
            use_cache: 是否使用缓存
            verbose: 是否输出日志
            
        Returns:
            VideoFeatures 对象
        """
        video_path = str(Path(video_path).resolve())
        file_name = Path(video_path).name
        
        # 尝试从缓存获取
        if use_cache and self.cache:
            cached = self.cache.get(video_path)
            if cached:
                if verbose:
                    print(f"  [缓存命中] {file_name}")
                return cached
        
        if verbose:
            print(f"  [提取特征] {file_name}")
        
        # 打开视频
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        try:
            # 获取视频基本信息
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            # 计算采样位置
            sample_positions = self._get_sample_positions(frame_count)
            
            # 提取特征
            phashes = []
            dhashes = []
            histograms = []
            
            for pos in sample_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                
                if not ret:
                    continue
                
                # 计算哈希
                phash, dhash = self._compute_frame_hashes(frame)
                phashes.append(phash)
                dhashes.append(dhash)
                
                # 计算直方图
                hist = self._compute_histogram(frame)
                histograms.append(hist)
        
        finally:
            cap.release()
        
        # 计算文件哈希
        file_hash = self.cache.get_file_hash(video_path) if self.cache else ""
        
        # 创建特征对象
        features = VideoFeatures(
            file_path=video_path,
            file_hash=file_hash,
            duration=duration,
            frame_count=frame_count,
            fps=fps,
            width=width,
            height=height,
            phashes=phashes,
            dhashes=dhashes,
            histograms=histograms,
            sample_positions=[p / frame_count for p in sample_positions] if frame_count > 0 else []
        )
        
        # 保存到缓存
        if use_cache and self.cache:
            self.cache.set(features)
        
        return features
