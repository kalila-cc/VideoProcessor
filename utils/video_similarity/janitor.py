# -*- coding: utf-8 -*-
"""
视频相似性判断 - 维护与清理工具
"""

import hashlib
from pathlib import Path
from typing import List
from .cache import FeatureCache
from .config import SimilarityConfig


class CacheJanitor:
    """
    缓存清理与维护工具类
    """
    
    def __init__(self, config: SimilarityConfig = None, cache: FeatureCache = None):
        """
        初始化清理工具
        
        Args:
            config: 配置对象
            cache: 缓存管理器实例
        """
        self.config = config or SimilarityConfig()
        self.cache = cache or FeatureCache(self.config.cache_dir)

    @staticmethod
    def get_cache_id(video_path: str) -> str:
        """
        根据视频路径生成缓存ID (必须与 FeatureCache 逻辑一致)
        """
        abs_path = str(Path(video_path).resolve())
        return hashlib.md5(abs_path.encode('utf-8')).hexdigest()[:16]

    def clean_orphans(self, video_files: List[str], dry_run: bool = True) -> dict:
        """
        清理无法对应到视频列表的孤立缓存数据
        
        Args:
            video_files: 当前有效的视频路径列表
            dry_run: 是否仅预览，不执行删除
            
        Returns:
            包含统计结果的字典
        """
        # 1. 计算有效 ID 集合
        valid_cache_ids = {self.get_cache_id(v) for v in video_files}
        
        # 2. 检查缓存目录
        cache_dir = self.cache.cache_dir
        if not cache_dir.exists():
            return {
                "status": "cache_dir_not_found",
                "deleted_count": 0,
                "freed_bytes": 0,
                "valid_count": len(valid_cache_ids)
            }

        # 3. 识别冗余文件
        all_cache_files = list(cache_dir.glob("*"))
        to_delete = []
        
        for cf in all_cache_files:
            # 忽略目录和正在写入的临时文件
            if cf.is_dir() or cf.suffix == '.tmp':
                continue
                
            # 特殊处理：强制清理旧版遗留的索引文件
            if cf.name == 'cache_index.json':
                to_delete.append(cf)
                continue
                
            # 处理特征 JSON 文件
            if cf.suffix == '.json':
                if cf.stem not in valid_cache_ids:
                    to_delete.append(cf)
            else:
                # 非预期的文件类型也标记为冗余
                to_delete.append(cf)

        # 4. 执行删除
        freed_bytes = 0
        deleted_count = 0
        error_count = 0
        deleted_files = []
        
        for cf in to_delete:
            try:
                size = cf.stat().st_size
                if not dry_run:
                    cf.unlink()
                
                freed_bytes += size
                deleted_count += 1
                deleted_files.append(cf.name)
            except Exception:
                error_count += 1

        return {
            "status": "success",
            "valid_count": len(valid_cache_ids),
            "deleted_count": deleted_count,
            "error_count": error_count,
            "freed_bytes": freed_bytes,
            "deleted_files": deleted_files,
            "dry_run": dry_run
        }

    def check_health(self, video_files: List[str]) -> dict:
        """
        检查视频库特征提取的健康状况（找出缺失特征的视频）
        
        Args:
            video_files: 视频路径列表
            
        Returns:
            包含健康报告的字典
        """
        missing_list = []
        for v in video_files:
            if not self.cache.has(v):
                missing_list.append(v)
        
        return {
            "total_count": len(video_files),
            "missing_count": len(missing_list),
            "missing_list": missing_list,
            "health_score": (1 - len(missing_list) / len(video_files)) if video_files else 1.0
        }
