#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视频相似性判断运行脚本

用法：
    python run_similarity.py                # 使用配置的目录列表运行
    python run_similarity.py -d <目录1> <目录2>  # 指定目录列表
    python run_similarity.py -d <已有库> -i <新增目录>  # 增量模式
    python run_similarity.py --clear-cache  # 清除所有缓存
    python run_similarity.py --clean-orphan-cache  # 清理无法对应视频的孤立缓存
    python run_similarity.py --cache-stats  # 查看缓存统计

配置：
    修改 VIDEO_DIRECTORIES 列表，指定要扫描的视频目录
    或在 config/video_processor.json 中配置 base_dirs 和 incremental_dirs
"""

import sys
import argparse
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# 添加模块路径（指向项目根目录）
sys.path.insert(0, str(PROJECT_ROOT))

from utils.video_similarity import VideoSimilarityChecker, SimilarityConfig, CacheJanitor
from utils.video_similarity.reporter import VideoSimilarityReporter
from utils.video_similarity.server import run_server
import webbrowser
import json


# ============== 配置区域 ==============

# 要扫描的视频目录列表（请根据实际情况修改）
VIDEO_DIRECTORIES = [
    # r"D:\Videos\待整理",
    # r"E:\Downloads\视频",
    # 添加更多目录...
]

# 相似度阈值从 config/video_processor.json 的 similarity.similarity_medium 字段读取。

# 缓存目录（设为 None 使用默认位置，优先读取配置）
CACHE_DIR = None

# 输出目录默认从 config/video_processor.json 读取。
DEFAULT_OUTPUT_DIR = None

# ======================================


def format_duration(seconds: float) -> str:
    """格式化时长"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def format_file_size(file_path: str) -> str:
    """获取文件大小"""
    try:
        size = Path(file_path).stat().st_size
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"
    except:
        return "N/A"


def format_pair_output(pair: dict, index: int) -> str:
    """格式化单对相似视频的输出"""
    video_a = pair['video_a']
    video_b = pair['video_b']
    details = pair['details']
    
    lines = [
        f"[{index}] {pair['score']:.0%} {pair['level']}",
        f"  A: {video_a['name']}",
        f"     时长: {format_duration(video_a['duration'])} | 分辨率: {video_a['resolution']} | 大小: {format_file_size(video_a['path'])}",
        f"     {video_a['path']}",
        f"  B: {video_b['name']}",
        f"     时长: {format_duration(video_b['duration'])} | 分辨率: {video_b['resolution']} | 大小: {format_file_size(video_b['path'])}",
        f"     {video_b['path']}",
    ]
    
    # 如果分辨率不同，标记差异
    if video_a['resolution'] != video_b['resolution']:
        lines.append(f"  ⚠ 分辨率不同: {video_a['resolution']} vs {video_b['resolution']}")
    
    return '\n'.join(lines)


def write_log(similar_pairs: list, directories: list, threshold: float, 
              video_count: int, cached_count: int, log_file: Path):
    """
    写入日志文件（覆盖模式）
    
    Args:
        similar_pairs: 相似视频对列表
        directories: 扫描的目录列表
        threshold: 相似度阈值
        video_count: 视频总数
        cached_count: 缓存数量
        log_file: 日志文件路径
    """
    # 确保日志目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("视频相似性检查结果\n")
        f.write("=" * 60 + "\n")
        f.write(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"相似度阈值: {threshold:.0%}\n")
        f.write(f"扫描目录:\n")
        for d in directories:
            f.write(f"  - {d}\n")
        f.write(f"视频总数: {video_count}\n")
        f.write(f"比较对数: {video_count * (video_count - 1) // 2}\n")
        f.write(f"已缓存特征: {cached_count}\n")
        f.write("\n")
        
        if not similar_pairs:
            f.write("未发现相似视频\n")
        else:
            f.write(f"发现 {len(similar_pairs)} 对相似视频:\n")
            f.write("-" * 60 + "\n")
            
            for i, pair in enumerate(similar_pairs, 1):
                f.write("\n" + format_pair_output(pair, i) + "\n")
        
        f.write("\n" + "=" * 60 + "\n")
    
    return log_file


def run_cache_clean(checker, dry_run: bool):
    """
    清理孤立缓存文件 (使用 CacheJanitor 工具类)
    """
    janitor = CacheJanitor(checker.config, checker.cache)
    
    # 获取需要检查的视频文件（基于配置目录）
    directories = list(set((checker.config.base_dirs or []) + (checker.config.incremental_dirs or [])))
    if not directories:
        print("提示: 配置文件中未定义扫描目录，清理精度可能受限。")
        video_files = []
    else:
        print(f"正在扫描视频库以建立有效索引: {directories}")
        video_files = checker.collect_videos_from_directories(directories)
    
    results = janitor.clean_orphans(video_files, dry_run=dry_run)
    
    print("-" * 60)
    if results['status'] == 'success':
        print(f"统计结果:")
        print(f"  有效视频数: {results['valid_count']}")
        print(f"  {'待清理' if dry_run else '已清理'}文件数: {results['deleted_count']}")
        
        freed = results['freed_bytes']
        unit = "MB" if freed > 1024*1024 else "KB"
        size_val = freed / (1024*1024) if unit == "MB" else freed / 1024
        
        status_text = "预览完成，预计释放" if dry_run else "清理完成，共释放"
        print(f"  {status_text}: {size_val:.2f} {unit}")
    else:
        print(f"清理过程中出现异常: {results.get('status')}")
    print("-" * 60)


def run_similarity_check(directories: list, cache_dir: str = None, 
                        output_dir: str = None):
    """
    运行视频相似性检查
    
    Args:
        directories: 目录路径列表
        cache_dir: 缓存目录
        output_dir: 输出目录
    
    Note:
        阈值从 config/video_processor.json 的 similarity.similarity_medium 字段读取
    """
    
    if not directories:
        print("\n" + "!"*60)
        print("错误: 未指定视频目录！")
        print("请提供以下任一设置：")
        print("1. 修改 scripts/run_similarity.py 中的 VIDEO_DIRECTORIES 列表")
        print("2. 使用命令行参数 -d, 例如: python scripts/run_similarity.py -d D:\\Movies")
        print("!"*60 + "\n")
        return False
    
    # 初始化 Checker（会自动加载配置）
    checker = VideoSimilarityChecker(cache_dir=cache_dir)
    output_dir = output_dir or checker.config.output_dir
    threshold = checker.config.similarity_medium
    
    print(f"视频相似性检查 | 阈值: {threshold:.0%} | 目录: {len(directories)} 个")
    

    
    # 确定日志目录
    base_log_dir = Path(checker.config.log_dir)
    if not base_log_dir.is_absolute():
        # 如果是相对路径，则相对于当前工作目录
        base_log_dir = Path.cwd() / base_log_dir
    
    log_dir_path = base_log_dir / 'video_similarity'
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = log_dir_path / 'result.log'
    
    print(f"视频相似性检查 | 阈值: {threshold:.0%} | 目录: {len(directories)} 个")
    print(f"日志文件: {log_file}")
    
    # 收集视频文件
    video_files = checker.collect_videos_from_directories(directories)
    
    if not video_files:
        print("\n" + "!"*60)
        print(f"提示: 在指定目录中未找到任何视频文件。")
        print(f"扫描目录: {', '.join(directories)}")
        print("!"*60 + "\n")
        return False
    
    total_pairs = len(video_files) * (len(video_files) - 1) // 2
    print(f"找到 {len(video_files)} 个视频，共 {total_pairs} 对待比较")
    
    # 查找所有相似视频对（阈值使用配置文件中的 similarity_medium）
    similar_pairs = checker.find_all_similar_pairs(video_files)
    
    # 获取缓存数量
    cached_count = checker.get_cache_stats()['count']
    
    # 控制台输出精简结果
    if not similar_pairs:
        print(f"\n未发现相似视频")
    else:
        print(f"\n发现 {len(similar_pairs)} 对相似视频:")
        for i, pair in enumerate(similar_pairs, 1):
            video_a = pair['video_a']
            video_b = pair['video_b']
            print(f"  [{i}] {pair['score']:.0%} {video_a['name']} <-> {video_b['name']}")
    
    # 写入详细日志
    # 注意：这里需要传入完整的 log_file 路径
    write_log(similar_pairs, directories, threshold, len(video_files), cached_count, log_file)
    print(f"\n完成，详细日志已保存: {log_file}")
    
    # 生成操作报告
    checker.generate_report(similar_pairs, output_dir)
    return True


def run_incremental_check(base_dirs: list, incremental_dirs: list, 
                          cache_dir: str = None, output_dir: str = None):
    """
    运行增量视频相似性检查（新视频 vs 已有库）
    
    Args:
        base_dirs: 已有视频库目录列表
        incremental_dirs: 新增视频目录列表
        cache_dir: 缓存目录
        output_dir: 输出目录
    
    Note:
        阈值从 config/video_processor.json 的 similarity.similarity_medium 字段读取
    """
    
    if not base_dirs:
        print("\n" + "!"*60)
        print("错误: 增量模式需要指定已有视频库目录 (-d)")
        print("用法: python run_similarity.py -d <已有库> -i <新增目录>")
        print("!"*60 + "\n")
        return False
    
    if not incremental_dirs:
        print("\n" + "!"*60)
        print("错误: 增量模式需要指定新增视频目录 (-i)")
        print("!"*60 + "\n")
        return False
    
    # 初始化 Checker（会自动加载配置）
    checker = VideoSimilarityChecker(cache_dir=cache_dir)
    output_dir = output_dir or checker.config.output_dir
    threshold = checker.config.similarity_medium
    
    print(f"增量相似性检查 | 阈值: {threshold:.0%}")
    print(f"  已有库: {len(base_dirs)} 个目录")
    print(f"  新增目录: {len(incremental_dirs)} 个目录")
    
    # 确定日志目录
    base_log_dir = Path(checker.config.log_dir)
    if not base_log_dir.is_absolute():
        base_log_dir = Path.cwd() / base_log_dir
    
    log_dir_path = base_log_dir / 'video_similarity'
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = log_dir_path / 'incremental_result.log'
    
    print(f"日志文件: {log_file}")
    
    # 收集视频文件
    existing_videos = checker.collect_videos_from_directories(base_dirs)
    new_videos = checker.collect_videos_from_directories(incremental_dirs)
    
    if not existing_videos:
        print("\n" + "!"*60)
        print("提示: 已有库目录中未找到任何视频文件。")
        print(f"扫描目录: {', '.join(base_dirs)}")
        print("!"*60 + "\n")
        return False
    
    if not new_videos:
        print("\n" + "!"*60)
        print("提示: 新增目录中未找到任何视频文件。")
        print(f"扫描目录: {', '.join(incremental_dirs)}")
        print("!"*60 + "\n")
        return False
    
    total_pairs = len(new_videos) * len(existing_videos)
    print(f"已有库: {len(existing_videos)} 个视频")
    print(f"新增视频: {len(new_videos)} 个视频")
    print(f"待比对: {total_pairs} 对 (新 × 已有)")
    
    # 增量比对（阈值使用配置文件中的 similarity_medium）
    similar_pairs = checker.find_incremental_similar_pairs(
        new_videos, existing_videos
    )
    
    # 获取缓存数量
    cached_count = checker.get_cache_stats()['count']
    
    # 控制台输出精简结果
    if not similar_pairs:
        print(f"\n未发现相似视频")
    else:
        print(f"\n发现 {len(similar_pairs)} 对相似视频:")
        for i, pair in enumerate(similar_pairs, 1):
            video_a = pair['video_a']
            video_b = pair['video_b']
            print(f"  [{i}] {pair['score']:.0%} [新] {video_a['name']} <-> [库] {video_b['name']}")
    
    # 写入日志
    all_dirs = base_dirs + incremental_dirs
    write_log(similar_pairs, all_dirs, threshold, 
              len(existing_videos) + len(new_videos), cached_count, log_file)
    print(f"\n完成，详细日志已保存: {log_file}")
    
    # 生成报告
    checker.generate_report(similar_pairs, output_dir)
    return True


def refresh_report_html_from_data(output_dir: Path) -> bool:
    """Regenerate index.html from the current template and existing data.json."""
    output_dir = Path(output_dir)
    data_file = output_dir / 'data.json'
    if not data_file.exists():
        return False

    with open(data_file, 'r', encoding='utf-8') as f:
        report_data = json.load(f)
    VideoSimilarityReporter.generate_html_report(report_data, output_dir)
    return True


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='视频相似性判断工具 - 查找目录中可能相似的视频文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python run_similarity.py                     使用配置的目录列表运行
  python run_similarity.py -d D:\\Videos E:\\Downloads  指定多个目录
  python run_similarity.py -d D:\\Library -i D:\\New   增量模式 (新视频与已有库比对)
  python run_similarity.py --cache-stats       查看缓存统计
  python run_similarity.py --clear-cache       清除所有特征缓存
  python run_similarity.py --clean-orphan-cache 清理孤立特征缓存 (无法匹配视频的文件)
阈值配置:
  相似度阈值从 config/video_processor.json 的 similarity.similarity_medium 字段读取
        '''
    )
    
    parser.add_argument(
        '-d', '--directories',
        nargs='+',
        type=str,
        help='要扫描的视频目录列表'
    )

    parser.add_argument(
        '--cache-dir',
        type=str,
        default=CACHE_DIR,
        help='缓存目录路径'
    )
    parser.add_argument(
        '--cache-stats',
        action='store_true',
        help='显示缓存统计信息'
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='清除特征缓存'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='输出目录；不指定时读取 config/video_processor.json 的 output_dir'
    )
    parser.add_argument(
        '--clean-orphan-cache',
        action='store_true',
        help='清理孤立缓存 (无法对应到库中任何视频的特征文件)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式：用于缓存清理等支持预览的操作'
    )
    
    parser.add_argument(
        '-i', '--incremental',
        nargs='+',
        type=str,
        help='增量模式: 指定新增视频目录 (仅与 -d 指定的已有库比对)'
    )
    
    parser.add_argument(
        '--server', '-S',
        action='store_true',
        help='处理完成后启动交互式 Web 界面查看结果'
    )
    
    parser.add_argument(
        '--server-only',
        action='store_true',
        help='跳过相似度分析，直接启动 Web 服务器（需已有 data.json）'
    )
    
    args = parser.parse_args()
    
    # --- 交互式引导：无参数且存在旧报告时，询问是否启动 Server ---
    if len(sys.argv) == 1:
        # 获取默认输出目录（参考 config 或 DEFAULT_OUTPUT_DIR）
        checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
        out_dir = Path(args.output if args.output else checker.config.output_dir)
        data_file = out_dir / 'data.json'
        
        if data_file.exists():
            print(f"\n[提示] 检测到已存在历史分析报告 ({data_file.name})")
            choice = input("是否直接启动交互式 Web 界面查看？[Y/n]: ").strip().lower()
            
            # 默认回车或输入 Y/yes 为 True
            if choice in ['', 'y', 'yes']:
                print(f"[System] 正在使用最新代码模板刷新 UI 界面...")
                try:
                    refresh_report_html_from_data(out_dir)
                    args.server_only = True
                except Exception as e:
                    print(f"[Error] 刷新 UI 失败: {e}")
                    # 如果刷新失败但 index.html 还在，尝试继续
                    if not (out_dir / 'index.html').exists():
                        print("错误: 缺失 index.html，无法启动服务器。")
                        return
                    args.server_only = True

    # 优先处理 server-only 模式（跳过分析，直接启动服务器）
    if args.server_only:
        checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
        output_dir = args.output if args.output else checker.config.output_dir
        
        # 预检
        data_file = Path(output_dir) / 'data.json'
        index_file = Path(output_dir) / 'index.html'

        if data_file.exists():
            try:
                print(f"[System] 正在使用最新代码模板刷新 UI 界面...")
                refresh_report_html_from_data(Path(output_dir))
            except Exception as e:
                print(f"[Warning] 刷新 UI 失败，将尝试使用现有 index.html: {e}")
        
        if not data_file.exists() or not index_file.exists():
            print("\n" + "!"*60)
            print(f"错误: 无法启动服务器，输出目录缺失必要文件。")
            print(f"检查目录: {output_dir}")
            print("建议: 请运行一次完整的相似度扫描来生成报告。")
            print("!"*60 + "\n")
            return
        
        url = "http://localhost:8000"
        print(f"\n[System] 正在启动 Web 界面: {url}")
        
        try:
            webbrowser.open(url)
        except:
            pass
            
        run_server(output_dir)
        return
    
    # 处理缓存相关命令
    if args.cache_stats:
        checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
        janitor = CacheJanitor(checker.config, checker.cache)
        
        # 基础统计
        stats = checker.get_cache_stats()
        print("\n" + "=" * 40)
        print("缓存基础统计:")
        print(f"  缓存文件数: {stats['count']}")
        print(f"  占用空间:   {stats['total_size_mb']} MB")
        print(f"  存储目录:   {stats['cache_dir']}")
        
        # 健康检查 (查找库中缺失的特征)
        base_dirs = args.directories or checker.config.base_dirs or VIDEO_DIRECTORIES
        video_files = checker.collect_videos_from_directories(base_dirs)
        
        if video_files:
            health = janitor.check_health(video_files)
            print("\n库特征覆盖报告:")
            print(f"  视频总数:   {health['total_count']}")
            print(f"  已缓存特征: {health['total_count'] - health['missing_count']}")
            print(f"  缺失特征:   {health['missing_count']}")
            print(f"  健康度:     {health['health_score']:.1%}")
            
            if health['missing_count'] > 0:
                print(f"\n提示: 有 {health['missing_count']} 个视频尚未提取特征。")
                print("运行相似度扫描时会自动补全缺失特征。")
        
        print("=" * 40 + "\n")
        return
    
    if args.clear_cache:
        checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
        checker.clear_cache()
        print("缓存已清除")
        return
    
    if args.clean_orphan_cache:
        checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
        run_cache_clean(checker, args.dry_run)
        return
    
    # 确定使用的目录列表（命令行优先，其次 config，最后脚本常量）
    checker = VideoSimilarityChecker(cache_dir=args.cache_dir)
    
    # 基础目录
    if args.directories:
        base_dirs = args.directories
    elif checker.config.base_dirs:
        base_dirs = checker.config.base_dirs
    else:
        base_dirs = VIDEO_DIRECTORIES
    
    # 增量目录
    if args.incremental:
        incremental_dirs = args.incremental
    elif checker.config.incremental_dirs:
        incremental_dirs = checker.config.incremental_dirs
    else:
        incremental_dirs = []
    
    # 决定运行模式
    if incremental_dirs:
        # 增量模式
        success = run_incremental_check(
            base_dirs=base_dirs,
            incremental_dirs=incremental_dirs,
            cache_dir=args.cache_dir,
            output_dir=args.output
        )
    else:
        # 全量模式
        success = run_similarity_check(
            directories=base_dirs,
            cache_dir=args.cache_dir,
            output_dir=args.output
        )

    if args.server and success:
        output_dir = args.output if args.output else checker.config.output_dir
        url = "http://localhost:8000"
        print(f"\n[System] 扫描完成，正在启动 Web 界面: {url}")
        
        try:
            webbrowser.open(url)
        except:
            pass
            
        run_server(output_dir)


if __name__ == "__main__":
    main()

