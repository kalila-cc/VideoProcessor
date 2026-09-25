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

   如果服务已经在运行，脚本会直接打开浏览器页面；否则会在后台启动服务，等待就绪后打开页面。关闭启动窗口或浏览器不会结束后台任务。首次启动不需要已有报告。

   命令行方式：

   ```powershell
   cd D:\Projects\DownloadVideoProcessor
   python scripts\run_similarity.py --server-only
   ```

2. 打开 `http://localhost:8000`。

3. 在默认的 `下载整理` 页按流程处理新视频。

   - `按大小分组并重命名`：将下载根目录中的视频移动到配置的 8 个大小分组目录，并按创建时间命名。
   - `与视频库比对`：将下载区与视频库比较；如有未分组视频，确认后先分组并重命名。重新比对会替换当前审阅列表。
   - `进入审阅`：双视频同步预览，顶部标明“下载区／视频库”。每侧红色 `删除此视频` 只删除该侧视频并移入 Windows 回收站；`均保留并忽略此组` 保存忽略决定。
   - `移动到视频库`：将下载区已分组的视频移入视频库并复用或生成特征缓存，下载区不再保留这些文件。尚有待审阅组时会提示。

4. 在 `视频库` 页查看 8 组数量／容量分布，以及按对数区间统计的大小直方图和累计占比。

5. 在 `维护与记录` 页查看或清空最近 20 次任务记录，执行库内比对、重建缓存索引、计算缺失特征。无用缓存数量和可释放空间直接显示，可刷新或删除。

分类、比对、移动和缓存写操作均在后台任务中执行，任务期间可以切页或刷新。页面显示服务连接状态并自动重连。后端被关闭后，未完成任务会标记为中断，需要核对文件状态后重新发起，不会自动重复文件操作。

新版操作说明和验证方式见 [Web 工作台说明](docs/WEB_WORKSPACE_V2.md)。

## 脚本入口

日常使用 Web 工作台，CLI 与离线维护入口如下：

| 脚本 | 用途 |
| --- | --- |
| `scripts/run_similarity.py` | 相似检测、缓存维护、Web 工作台启动 |
| `scripts/start_web.ps1` | 后台启动并等待服务就绪；`-NoBrowser` 不打开浏览器 |
| `scripts/rebuild_cache_index.py` | 校验当前格式特征并重建内容索引 |
| `scripts/regroup_library.py` | 停服后规划或执行 8 组目录迁移，支持中断续跑 |

常用命令：

```powershell
python scripts\run_similarity.py --server-only
python scripts\run_similarity.py
python scripts\run_similarity.py --cache-stats
python scripts\run_similarity.py --clean-orphan-cache --dry-run
```

旧的 `run_renamer.py`、`run_mover.py`、`run_pipeline.py` 和 `operation.md` 流程已经移除；对应能力已并入 Web 工作台。清理记录见 `docs/LEGACY_CLEANUP.md`。

## 重新生成相似检测报告

当前 Web 页面读取 `output/video_similarity/data.json` 和 `index.html`。需要刷新相似对时，优先在 `下载整理` 页点击 `与视频库比对`，或在 `相似审阅` 页点击 `下载区与视频库比对`；页面会显示后台刷新状态，并在完成后重新载入当前可处理的视频组。

维护页的 `比对视频库内部重复项` 会对视频库内所有视频做两两比较，数量为 `n * (n - 1) / 2`，视频库较大时只建议低频使用。

也可以在命令行运行：

```powershell
python scripts\run_similarity.py
```

也可以显式指定已有库和新增目录：

```powershell
python scripts\run_similarity.py -d "D:\Private\Videos" -i "C:\Users\Chris\Downloads\01_0-2MiB"
```

## 目录说明

- `config/`：统一配置。
- `scripts/`：当前 CLI 入口。
- `utils/video_similarity/`：相似检测、报告生成、Web 服务、下载整理 API。
- `cache/`：相似检测特征缓存，可重建但重建耗时。
- `output/`：当前 Web 报告、任务历史和本地维护备份。
- `logs/`：历史运行日志。
- `docs/`：当前架构、操作流程和清理记录。

特征只接受当前 v2 格式；路径变化后的缓存复用机制见 [缓存说明](docs/CACHE_REUSE.md)。视频、缓存、报告、日志及本地备份不纳入 Git。测试命令见 [工作台验证说明](docs/WEB_WORKSPACE_V2.md#部署和验证)。
