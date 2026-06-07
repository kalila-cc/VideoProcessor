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
- `cache.py`：管理视频特征缓存。
- `extractor.py`：抽帧并计算 pHash、dHash、颜色直方图等特征。
- `checker.py`：协调扫描、特征提取和相似度计算。
- `reporter.py`：生成 Web 使用的 `data.json` 和 `index.html`。
- `server.py`：本地 Web 服务，支持视频预览、相似检测后台刷新、真实删除、下载整理、迁移入库和缓存写入。
- `templates/report_template.html`：Web 工作台页面模板。

## 常用入口

从项目根目录运行：

```powershell
python scripts\run_similarity.py --server-only
python scripts\run_similarity.py
python scripts\run_similarity.py --cache-stats
```

Web `视频对比` 页的 `重新扫描比对` 按钮会在后台调用同一脚本入口刷新报告，完成后重新载入当前会话数据。

代码调用：

```python
from utils.video_similarity import VideoSimilarityChecker

checker = VideoSimilarityChecker()
videos = checker.collect_videos_from_directories(checker.config.base_dirs)
pairs = checker.find_all_similar_pairs(videos, threshold=checker.config.similarity_medium)
```

## 缓存

特征缓存目录由 `config/video_processor.json` 的 `cache_dir` 字段控制。默认是项目根目录下的 `cache/video_similarity`。
