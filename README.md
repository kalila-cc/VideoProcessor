# DownloadVideoProcessor

`DownloadVideoProcessor` 是本地视频下载后处理项目。当前主流程已经收敛到一个 Web 工作台：查看下载目录分布、按大小分类、按创建时间规范命名、迁移到视频库并写入相似检测特征缓存，同时审阅和删除相似视频。

所有运行路径、视频规格映射、缓存位置、报告输出位置和相似检测参数统一由 `config/video_processor.json` 维护。

## 数据位置

- 下载目录：`C:\Users\Chris\Downloads`
- 视频库：`D:\Private\Videos`
- 项目目录：`D:\Projects\DownloadVideoProcessor`
- 统一配置：`config/video_processor.json`
- 特征缓存：`cache/video_similarity`
- Web 报告输出：`output/video_similarity`

## 当前主流程

1. 启动 Web 工作台。

   双击项目根目录的：

   ```text
   start_web.bat
   ```

   如果服务已经在运行，脚本会直接打开浏览器页面；如果没有运行，会在当前窗口启动后端服务。

   命令行方式：

   ```powershell
   cd D:\Projects\DownloadVideoProcessor
   python scripts\run_similarity.py --server-only
   ```

2. 打开 `http://localhost:8000`。

3. 在 `下载整理` 页处理下载目录。

   - `一键分类`：把下载根目录中的视频移动到 `XS/S/M/L/XL`，并立即规范命名。
   - `一键规范命名`：单独处理已分类目录中的历史文件。
   - `一键迁移并缓存`：先规范命名，再移动到 `D:\Private\Videos` 对应规格目录，并写入相似检测特征缓存。

4. 在 `视频库概览` 页查看最终视频库规格数量、占比和大小分布。

5. 在 `视频比对` 页审阅相似视频。

   - `增量比对下载区`：将下载区规格目录中的视频与现有视频库做增量比对，适合日常处理新下载视频。
   - `全库重新扫描`：对整个视频库重新做两两相似扫描，视频多时会很慢，作为低频维护操作。
   - `预览孤立缓存` / `清理孤立缓存`：找出或删除无法对应到现存视频路径的特征缓存，不会删除视频文件。
   - `删除此视频`：真实删除本地文件，不是标记待删除。

## 脚本入口

当前只保留一个脚本入口：

| 脚本 | 用途 |
| --- | --- |
| `scripts/run_similarity.py` | 相似检测、缓存维护、Web 工作台启动 |

常用命令：

```powershell
python scripts\run_similarity.py --server-only
python scripts\run_similarity.py
python scripts\run_similarity.py --cache-stats
python scripts\run_similarity.py --clean-orphan-cache --dry-run
```

旧的 `run_renamer.py`、`run_mover.py`、`run_pipeline.py` 和 `operation.md` 流程已经移除；对应能力已并入 Web 工作台。清理记录见 `docs/LEGACY_CLEANUP.md`。

## 重新生成相似检测报告

当前 Web 页面读取 `output/video_similarity/data.json` 和 `index.html`。需要刷新相似对时，优先在 Web 的 `视频比对` 页点击 `增量比对下载区`；页面会显示后台刷新状态，并在完成后重新载入当前可处理的视频组。

`全库重新扫描` 会对视频库内所有视频做两两比较，数量为 `n * (n - 1) / 2`，视频库较大时只建议低频使用。

也可以在命令行运行：

```powershell
python scripts\run_similarity.py
```

也可以显式指定已有库和新增目录：

```powershell
python scripts\run_similarity.py -d D:\Private\Videos\0_XS(0MB_10MB) D:\Private\Videos\1_S(10MB_20MB) D:\Private\Videos\2_M(20MB_40MB) D:\Private\Videos\3_L(40MB_200MB) D:\Private\Videos\4_XL(200MB_INF) -i C:\Users\Chris\Downloads\XS C:\Users\Chris\Downloads\S C:\Users\Chris\Downloads\M C:\Users\Chris\Downloads\L C:\Users\Chris\Downloads\XL
```

## 目录说明

- `config/`：统一配置。
- `scripts/`：当前 CLI 入口。
- `utils/video_similarity/`：相似检测、报告生成、Web 服务、下载整理 API。
- `cache/`：相似检测特征缓存，可重建但重建耗时。
- `output/`：当前 Web 报告数据和页面。
- `logs/`：历史运行日志。
- `docs/`：当前架构、操作流程和清理记录。
