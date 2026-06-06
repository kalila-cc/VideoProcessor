# -*- coding: utf-8 -*-
"""
视频相似性判断 - 特征数据结构模块
"""

from dataclasses import dataclass
import numpy as np
import imagehash


@dataclass
class VideoFeatures:
    """视频特征数据"""
    
    file_path: str           # 视频文件路径
    file_hash: str           # 文件内容哈希（用于缓存标识）
    duration: float          # 视频时长（秒）
    frame_count: int         # 总帧数
    fps: float               # 帧率
    width: int               # 视频宽度
    height: int              # 视频高度
    phashes: list            # 感知哈希列表（每帧一个）
    dhashes: list            # 差异哈希列表
    histograms: list         # 颜色直方图列表
    sample_positions: list   # 采样帧的时间位置（百分比）

    def to_dict(self) -> dict:
        """转换为可序列化的字典"""
        return {
            'file_path': self.file_path,
            'file_hash': self.file_hash,
            'duration': self.duration,
            'frame_count': self.frame_count,
            'fps': self.fps,
            'width': self.width,
            'height': self.height,
            'phashes': [str(h) for h in self.phashes],
            'dhashes': [str(h) for h in self.dhashes],
            'histograms': [h.tolist() for h in self.histograms],
            'sample_positions': self.sample_positions
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VideoFeatures':
        """从字典恢复"""
        return cls(
            file_path=data['file_path'],
            file_hash=data['file_hash'],
            duration=data['duration'],
            frame_count=data['frame_count'],
            fps=data['fps'],
            width=data['width'],
            height=data['height'],
            phashes=[imagehash.hex_to_hash(h) for h in data['phashes']],
            dhashes=[imagehash.hex_to_hash(h) for h in data['dhashes']],
            histograms=[np.array(h, dtype=np.float32) for h in data['histograms']],
            sample_positions=data['sample_positions']
        )
    
    @property
    def resolution(self) -> str:
        """获取分辨率字符串"""
        return f"{self.width}x{self.height}"
    
    @property
    def duration_str(self) -> str:
        """获取格式化的时长字符串"""
        minutes = int(self.duration // 60)
        seconds = int(self.duration % 60)
        return f"{minutes}:{seconds:02d}"
