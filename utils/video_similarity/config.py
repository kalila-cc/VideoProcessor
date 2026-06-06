# -*- coding: utf-8 -*-
"""
视频相似性判断 - 配置模块
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class SimilarityConfig:
    """相似度计算配置"""
    
    # 采样帧数配置
    num_sample_frames: int = 15
    
    # 特征权重
    weight_duration: float = 0.10
    weight_phash: float = 0.40
    weight_dhash: float = 0.20
    weight_histogram: float = 0.30
    
    # 阈值
    duration_threshold: float = 0.95
    similarity_high: float = 0.90
    similarity_medium: float = 0.80
    
    # 哈希大小
    hash_size: int = 16
    
    # 直方图配置
    hist_bins: int = 64
    
    # 并行配置
    max_workers: int = None  # 进程数，None表示自动使用CPU核心数

    # 路径配置
    output_dir: str = "output/video_similarity"
    cache_dir: str = "cache/video_similarity"
    log_dir: str = "logs"
    
    # 增量检测配置
    base_dirs: List[str] = field(default_factory=list)  # 已有视频库目录
    incremental_dirs: List[str] = field(default_factory=list)  # 新增视频目录
    
    # 视频文件扩展名
    video_extensions: List[str] = field(default_factory=lambda: [
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'
    ])
    
    def __post_init__(self):
        """初始化后尝试加载配置文件"""
        self.load_from_json()

    def load_from_json(self, config_path: str = None):
        """
        从 JSON 文件加载配置
        
        Args:
            config_path: 配置文件路径，默认使用模块同目录下的 config.json
        """
        if config_path is None:
            # 默认查找同级目录下的 config.json
            config_path = Path(__file__).parent / 'config.json'
        
        config_file = Path(config_path)
        if not config_file.exists():
            return
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 更新属性
            for key, value in data.items():
                if hasattr(self, key):
                    # 类型转换，确保类型一致（尤其是 tuple -> list）
                    if key == 'video_extensions' and isinstance(value, list):
                        value = list(value)
                    setattr(self, key, value)
                    
        except Exception as e:
            print(f"  [警告] 加载配置文件失败: {e}")

    def save_to_json(self, config_path: str = None):
        """保存当前配置到 JSON"""
        if config_path is None:
            config_path = Path(__file__).parent / 'config.json'
            
        data = {
            'output_dir': self.output_dir,
            'num_sample_frames': self.num_sample_frames,
            'weight_duration': self.weight_duration,
            'weight_phash': self.weight_phash,
            'weight_dhash': self.weight_dhash,
            'weight_histogram': self.weight_histogram,
            'duration_threshold': self.duration_threshold,
            'similarity_high': self.similarity_high,
            'similarity_medium': self.similarity_medium,
            'hash_size': self.hash_size,
            'hist_bins': self.hist_bins,
            'max_workers': self.max_workers,
            'cache_dir': self.cache_dir,
            'log_dir': self.log_dir,
            'base_dirs': self.base_dirs,
            'incremental_dirs': self.incremental_dirs,
            'video_extensions': self.video_extensions
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
