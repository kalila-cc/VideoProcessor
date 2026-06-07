# 日常操作流程

## 1. 启动 Web 工作台

```powershell
cd D:\Projects\DownloadVideoProcessor\scripts
python run_similarity.py --server-only
```

访问：

```text
http://localhost:8000
```

如果报告文件不存在，先运行一次相似检测：

```powershell
python run_similarity.py
```

## 2. 整理下载目录

进入 Web 左侧 `下载整理`。

- `刷新`：重新读取下载目录、视频库和特征缓存统计。
- `一键分类`：把 `C:\Users\Chris\Downloads` 根目录下的视频移动到 `XS/S/M/L/XL`，并按创建时间规范命名。
- `一键规范命名`：对 `XS/S/M/L/XL` 中已有视频做规范命名；已是时间戳格式且未与视频库冲突的文件会跳过。
- `一键迁移并缓存`：先规范命名，再移动到 `D:\Private\Videos` 对应规格目录，并为迁移后的视频写入相似检测特征缓存。

迁移和缓存写入是同步长任务，文件很多时页面会保持等待状态直到后端完成。

## 3. 查看视频库状态

进入 Web 左侧 `视频库概览`。

这里用于确认：

- 各规格视频数量和容量占比。
- 所有视频大小的对数分布。
- 最大视频和缓存覆盖概况。

## 4. 审阅和维护相似视频

进入 Web 左侧 `视频比对`。

- `增量比对下载区`：将 `C:\Users\Chris\Downloads\XS/S/M/L/XL` 中的视频与现有视频库做增量比对。日常处理新下载视频优先使用这个入口。
- `全库重新扫描`：对整个视频库做全量两两相似扫描，刷新 `output/video_similarity/data.json` 和页面会话数据。视频多时会很慢，只建议低频维护时使用。
- `预览孤立缓存`：扫描现存视频路径和特征缓存，查看可清理的无用缓存数量，不执行删除。
- `清理孤立缓存`：删除无法对应到现存视频路径的特征缓存文件，不删除视频文件；如果相似比对正在运行，Web 会阻止执行清理。
- `忽略此组`：只在 Web 报告层忽略相似对，不移动或删除视频。
- `删除此视频`：真实删除本地文件，并同步当前报告状态。
- 视频播放直接读取原始文件路径，不依赖复制文件。

## 5. 重新生成相似检测结果

优先在 Web 左侧 `视频比对` 点击 `增量比对下载区`。该操作会启动后台任务，页面显示最新状态，任务完成后自动重新载入可处理的视频组。

命令行方式同样默认读取 `config/video_processor.json`：

```powershell
cd D:\Projects\DownloadVideoProcessor\scripts
python run_similarity.py
```

指定已有库和新增目录：

```powershell
python run_similarity.py -d D:\Private\Videos\0_XS(0MB_10MB) D:\Private\Videos\1_S(10MB_20MB) D:\Private\Videos\2_M(20MB_40MB) D:\Private\Videos\3_L(40MB_200MB) D:\Private\Videos\4_XL(200MB_INF) -i C:\Users\Chris\Downloads\XS C:\Users\Chris\Downloads\S C:\Users\Chris\Downloads\M C:\Users\Chris\Downloads\L C:\Users\Chris\Downloads\XL
```

扫描完成后会更新：

- `output/video_similarity/data.json`
- `output/video_similarity/index.html`
- `logs/video_similarity/result.log` 或 `logs/video_similarity/incremental_result.log`

## 6. 缓存维护

优先在 Web 左侧 `视频比对` 使用：

- `预览孤立缓存`
- `清理孤立缓存`

命令行方式：

查看缓存统计：

```powershell
python run_similarity.py --cache-stats
```

预览孤立缓存清理：

```powershell
python run_similarity.py --clean-orphan-cache --dry-run
```

执行孤立缓存清理：

```powershell
python run_similarity.py --clean-orphan-cache
```

## 已移除的旧流程

不再使用：

- `run_renamer.py`
- `run_mover.py`
- `run_pipeline.py`
- 手工编辑 `output/video_similarity/operation.md`
- `run_similarity.py --prune`

这些能力已被 Web 的 `下载整理` 和 `视频对比` 页面替代。
