# -*- coding: utf-8 -*-
"""
视频相似性判断工具模块

基于多特征融合的轻量级视频相似度计算方案:
- 感知哈希 (pHash) - 内容结构相似性
- 差异哈希 (dHash) - 边缘/纹理相似性
- 颜色直方图 - 色彩分布相似性
- 视频时长 - 基础过滤
"""

from .config import SimilarityConfig
from .features import VideoFeatures
from .cache import FeatureCache
from .extractor import VideoFeatureExtractor
from .checker import VideoSimilarityChecker
from .janitor import CacheJanitor

__all__ = [
    'SimilarityConfig',
    'VideoFeatures',
    'FeatureCache',
    'VideoFeatureExtractor',
    'VideoSimilarityChecker',
    'CacheJanitor',
]
