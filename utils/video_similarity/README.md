# video_similarity

本模块负责视频相似检测、特征缓存、报告生成和本地 Web 工作台服务。

## 配置

模块不再维护独立配置文件。所有运行配置统一读取：

`config/video_processor.json`

其中包括：

- 下载目录和视频库目录
- 规格分区和归档目录映射
- 视频扩展名
- 特征缓存目录
- Web 报告输出目录
- 日志目录
- 相似检测采样、权重和阈值参数

## 主要文件

- `config.py`：读取统一配置并派生相似检测配置。
- `cache.py`：管理严格 v2 特征缓存、SQLite 内容索引和跨路径复用。
- `extractor.py`：抽帧并计算 pHash、dHash、颜色直方图等特征。
- `checker.py`：协调扫描、特征提取和相似度计算。
- `reporter.py`：生成 Web 使用的 `data.json` 和 `index.html`。
- `server.py`：本地 Web 服务，支持视频预览、增量/全量相似检测后台刷新、孤立缓存清理、移入 Windows 回收站、下载整理、迁移入库和缓存写入。
- `tasks.py`：后台任务互斥、进度、历史持久化与清空。
- `recycle.py`：Windows 回收站适配。
- `templates/report_template.html`：Web 工作台页面模板。
- `assets/`：工作台脚本和样式、双播放器同步、参数比较，以及本地 ArtPlayer 和 Chart.js。

## 常用入口

从项目根目录运行：

```powershell
python scripts\run_similarity.py --server-only
python scripts\run_similarity.py
python scripts\run_similarity.py --cache-stats
```

Web 提供两个后台比对入口，都会替换当前审阅列表：

- `下载整理 → 与视频库比对`：已有库使用视频库分组目录，新增目录使用下载区配置的 8 个大小分组目录。相似审阅页也提供同一入口。
- `维护与记录 → 比对视频库内部重复项`：只扫描视频库分组目录，执行全量两两比对。

维护页直接显示无用缓存数量、可释放空间和检查时间，提供刷新、删除缓存及清空任务记录入口。清空历史不影响当前比对结果。

代码调用：

```python
from utils.video_similarity import VideoSimilarityChecker

checker = VideoSimilarityChecker()
videos = checker.collect_videos_from_directories(checker.config.base_dirs)
pairs = checker.find_all_similar_pairs(videos, threshold=checker.config.similarity_medium)
```

## 缓存

特征缓存目录由 `config/video_processor.json` 的 `cache_dir` 字段控制。默认是项目根目录下的 `cache/video_similarity`。

缓存支持按文件身份和完整内容摘要找回已改名或移动的视频特征。运行时只接受完整的 v2 格式，不转换旧格式。维护页可使用“重建缓存索引”校验并索引当前特征，无需重新抽帧。首次跨盘复用准备需要完整读取视频一次；同盘改名通常走文件身份快速路径。详见 [缓存复用说明](../../docs/CACHE_REUSE.md)。
