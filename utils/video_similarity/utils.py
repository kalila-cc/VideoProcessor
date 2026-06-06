# -*- coding: utf-8 -*-
"""
视频相似性判断 - 通用工具函数
"""

from pathlib import Path


def format_duration(seconds: float) -> str:
    """
    格式化时长
    
    Args:
        seconds: 时长（秒）
        
    Returns:
        格式化的时长字符串，格式为 "分钟:秒"
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def format_file_size(file_path: str) -> str:
    """
    获取格式化的文件大小
    
    Args:
        file_path: 文件路径
        
    Returns:
        格式化的文件大小字符串（KB 或 MB）
    """
    try:
        size = Path(file_path).stat().st_size
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"
    except:
        return "N/A"
