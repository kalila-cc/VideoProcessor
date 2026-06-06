# -*- coding: utf-8 -*-
"""
视频相似性判断 - 特征缓存模块
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Optional

from .features import VideoFeatures


class FeatureCache:
    """
    视频特征缓存管理器
    
    使用文件哈希（基于文件头尾和大小）作为缓存标识，
    确保即使脚本重跑也能取到缓存值。
    """
    
    def __init__(self, cache_dir: str = None):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录路径，默认为当前目录下的 .video_similarity_cache
        """
        if cache_dir is None:
            # 默认缓存路径：项目根目录/cache/video_similarity
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cache_dir = os.path.join(root_dir, 'cache', 'video_similarity')
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # 废弃 cache_index.json，改为直接读取单文件
    
    def get_file_hash(self, file_path: str) -> str:
        """
        计算文件内容哈希
        
        使用文件头部 + 尾部 + 大小计算哈希，避免读取整个大文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件哈希字符串
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return ""
            file_size = file_path.stat().st_size
            
            hasher = hashlib.md5()
            hasher.update(str(file_size).encode())
            
            with open(file_path, 'rb') as f:
                # 读取文件头部 64KB
                hasher.update(f.read(65536))
                
                # 读取文件尾部 64KB
                if file_size > 131072:
                    f.seek(-65536, 2)
                    hasher.update(f.read(65536))
            
            return hasher.hexdigest()
        except Exception:
            return ""
    
    def _get_cache_id(self, video_path: str) -> str:
        """根据视频路径生成缓存ID (文件名)"""
        # 必须使用绝对路径以确保唯一性
        abs_path = str(Path(video_path).resolve())
        return hashlib.md5(abs_path.encode('utf-8')).hexdigest()[:16]
    
    def get(self, video_path: str) -> Optional[VideoFeatures]:
        """
        获取缓存的视频特征
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            VideoFeatures 或 None（如果缓存不存在或已过期）
        """
        try:
            cache_id = self._get_cache_id(video_path)
            cache_file = self.cache_dir / f"{cache_id}.json"
            
            if not cache_file.exists():
                return None
                
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 校验文件内容一致性
            current_hash = self.get_file_hash(video_path)
            if not current_hash: # 文件不存在
                return None
                
            if data.get('file_hash') != current_hash:
                return None # 文件内容已变更
                
            return VideoFeatures.from_dict(data)
            
        except (json.JSONDecodeError, IOError, KeyError):
            return None
    
    def set(self, features: VideoFeatures):
        """
        保存视频特征到缓存 (原子写入)
        
        Args:
            features: 视频特征对象
        """
        try:
            cache_id = self._get_cache_id(features.file_path)
            cache_file = self.cache_dir / f"{cache_id}.json"
            temp_file = self.cache_dir / f"{cache_id}.tmp"
            
            # 先写入临时文件，再重命名，确保跨进程/线程安全
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(features.to_dict(), f, ensure_ascii=False)
                
            temp_file.replace(cache_file)
            
        except Exception as e:
            print(f"写入缓存失败: {e}")
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def has(self, video_path: str) -> bool:
        """
        检查视频是否有有效缓存
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            是否有有效缓存
        """
        return self.get(video_path) is not None
    
    def clear(self):
        """清空所有缓存"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_stats(self) -> dict:
        """
        获取缓存统计信息 (直接统计文件)
        
        Returns:
            包含缓存数量、总大小等信息的字典
        """
        total_size = 0
        cache_count = 0
        
        try:
            for cache_file in self.cache_dir.glob('*.json'):
                if cache_file.name == 'cache_index.json':
                    continue # 忽略旧的索引文件
                try:
                    total_size += cache_file.stat().st_size
                    cache_count += 1
                except:
                    pass
        except Exception:
            pass
        
        return {
            'count': cache_count,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'cache_dir': str(self.cache_dir)
        }
