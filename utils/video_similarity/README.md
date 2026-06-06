# 视频相似性判断工具

基于多特征融合的轻量级视频相似度计算工具，无需 GPU，纯 CPU 即可运行。

## 原理

采用 **智能采样 + 多特征融合** 策略：

1. **时长预过滤** - 时长差异 >5% 直接排除
2. **智能采样** - 均匀采样 15 帧（含首/中/尾锚点帧）
3. **多特征提取**
   - 感知哈希 (pHash) - 内容结构相似性 (40%)
   - 差异哈希 (dHash) - 边缘纹理相似性 (20%)
   - 颜色直方图 - 色彩分布相似性 (30%)
   - 时长相似度 (10%)
4. **ArtPlayer 交互引擎 (New)**
   - **V3.2 同步算法**: 毫秒级主从切换逻辑，支持播放/暂停/跳进度/倍速同步。
   - **全屏自适应**: 完美支持原生全屏与网页全屏，退出全屏时自动强制对齐。
   - **差异可视化**: 直观对比分辨率、时长、文件大小，并提供智能保留建议。

## 安装依赖

```bash
pip install opencv-python imagehash Pillow numpy
```

## 快速开始

### 命令行使用

```bash
# 1. 交互式启动 (智能选择)
# 如果之前运行过且存在报告，直接运行将询问是否启动 Web 界面并自动刷新 UI
python scripts/run_similarity.py

# 2. 扫描目录查找相似视频
python scripts/run_similarity.py -d D:\Videos

# 3. 扫描多个目录
python scripts/run_similarity.py -d D:\Videos E:\Downloads

# 4. 设置相似度阈值（默认 80%）
python scripts/run_similarity.py -d D:\Videos -t 0.85

# 5. 查看缓存统计
python scripts/run_similarity.py --cache-stats

# 6. 清除缓存
python scripts/run_similarity.py --clear-cache
```

### 结果输出

- **控制台输出**：仅显示精简的进度和相似视频列表，便于快速查看。
- **日志文件**：详细结果保存至 `logs/video_similarity/result.log`（每次运行覆盖）。
  - 记录运行时间、阈值、扫描目录
  - 包含相似视频的完整路径、时长、分辨率、文件大小等详细信息
  - 自动标记分辨率存在差异的视频对

### 代码调用

```python
from utils.video_similarity import VideoSimilarityChecker

checker = VideoSimilarityChecker()

# 比较两个视频
result = checker.compare('video1.mp4', 'video2.mp4')
print(f"相似度: {result['score']:.0%}")  # 相似度: 94%
print(f"判定: {result['level']}")        # 判定: 高度相似

# 批量查找相似视频
videos = checker.collect_videos_from_directories(['D:\\Videos'])
pairs = checker.find_all_similar_pairs(videos, threshold=0.80)
for pair in pairs:
    print(f"{pair['video_a']['name']} <-> {pair['video_b']['name']}: {pair['score']:.0%}")
```

## 模块结构

```
utils/video_similarity/
├── __init__.py      # 模块入口
├── config.py        # 自动加载 config.json
├── config.json      # 配置文件 (可直接修改)
├── features.py      # VideoFeatures 特征数据结构
├── cache.py         # FeatureCache 缓存管理器
├── extractor.py     # VideoFeatureExtractor 特征提取器
├── checker.py       # VideoSimilarityChecker 核心检测器
├── reporter.py      # 生成交互式 HTML 报告
├── server.py        # 基于 ArtPlayer 的交互式对比服务器
├── templates/       # HTML 报告 UI 模板
└── README.md        # 本文档
```

## 核心类

### VideoSimilarityChecker

主要入口类，提供以下方法：

- `compare(video_a, video_b)` - 比较两个视频的相似度
- `find_similar(video, video_list)` - 查找与目标视频相似的视频
- `find_all_similar_pairs(video_list)` - 查找列表中所有相似视频对
- `collect_videos_from_directories(dirs)` - 从目录收集视频文件
- `get_cache_stats()` - 获取缓存统计
- `clear_cache()` - 清空缓存

### SimilarityReportHandler (server.py)

启动一个增强型的 Web 交互服务器：

- **高级同步**: 并在双视频窗口中实现毫秒级同步预览。
- **文件定位**: 提供“在文件夹中显示”按钮，自动打开资源管理器并选中指定视频。
- **智能清除**: 一键执行物理删除，并在内存/磁盘中实时更新列表状态。
- **稳定性防护**: 内置 BrokenPipe 和 ConnectionAborted 保护，支持详细的日志持久化。

### SimilarityConfig

配置自动从同级目录下的 `config.json` 加载。你可以直接修改该 JSON 文件来调整参数：

```json
{
  "num_sample_frames": 15,
  "weight_phash": 0.40,
  "similarity_high": 0.90,
  "//": "更多参数详见 config.json"
}
```

### 配置文件参数详解

所有参数均可在 `config.json` 中调整，无需修改代码。

### 配置文件参数详解

所有参数均可在 `config.json` 中调整，无需修改代码。

- **`num_sample_frames`** (int, 默认 15)
  - **采样帧数**。提取多少帧进行比对。建议 10-20 帧，太少不准，太多影响速度。包含首帧、尾帧和中点帧。

- **`weight_duration`** (float, 默认 0.10)
  - **时长权重**。时长相似度在总分中的占比。

- **`weight_phash`** (float, 默认 0.40)
  - **感知哈希 (pHash) 权重**。反映画面**结构/整体布局**的相似性。抗压缩、模糊能力强。

- **`weight_dhash`** (float, 默认 0.20)
  - **差异哈希 (dHash) 权重**。反映画面**梯度/边缘**的相似性。

- **`weight_histogram`** (float, 默认 0.30)
  - **直方图权重**。反映画面**色彩分布**的相似性。

- **`duration_threshold`** (float, 默认 0.95)
  - **时长过滤阈值**。时长相似度低于此值（约差异 >5%）直接判定为不相似，跳过后续计算。

- **`similarity_high`** (float, 默认 0.90)
  - **高度相似阈值**。总分高于此值判定为 `高度相似`。

- **`similarity_medium`** (float, 默认 0.80)
  - **可能相似阈值**。总分高于此值但低于高度阈值，判定为 `可能相似`。

- **`hash_size`** (int, 默认 16)
  - **哈希尺寸**。哈希指纹的精度。`16` 表示 16x16 矩阵。增加此值提高准确度但增加计算量。

- **`hist_bins`** (int, 默认 64)
  - **直方图直方条数**。色彩统计的细粒度。

- **`video_extensions`** (list)
  - **扫描文件扩展名**。支持的视频格式列表，如 `[".mp4", ".avi", ".mkv"]` 等。

- **`cache_dir`** (str, 默认 "cache/video_similarity")
  - **缓存目录路径**。支持相对路径（相对于项目根目录）或绝对路径。

- **`log_dir`** (str, 默认 "logs")
  - **日志目录路径**。支持相对路径（相对于当前运行目录）或绝对路径。

### 使用 SimilarityConfig 类

```python
from utils.video_similarity import SimilarityConfig, VideoSimilarityChecker

config = SimilarityConfig(
    num_sample_frames=20,
    similarity_high=0.95
)
checker = VideoSimilarityChecker(config=config)
```

## 缓存机制

- 视频特征自动缓存到项目根目录下的 `cache/video_similarity/` 目录
- 使用纯文件内容哈希命名 json 缓存文件，确保多进程安全
- 脚本重跑时自动读取缓存，跳过已处理的视频
- 视频文件变更后自动重新计算特征

## 相似度判定

- **≥ 90%** - 高度相似（几乎相同内容）
- **80% ~ 90%** - 可能相似（需人工确认）
- **< 80%** - 不相似

## 性能参考

| 视频数量 | 比较对数 | 耗时（首次） | 耗时（有缓存） |
|---------|---------|-------------|--------------|
| 43 | 903 | ~2 分钟 | ~30 秒 |
| 403 | 81003 | ~3-5 分钟 (多核并行) | ~5 秒 (内存比对) |

## 局限性

- 对大幅度剪辑、片段顺序调整的视频效果有限
- 不支持音频相似度判断
- 极短视频（<5 秒）可能误判
