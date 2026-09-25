# 架构说明

## 定位

`DownloadVideoProcessor` 是一个本地视频下载后处理工作台。项目目录保存代码、配置及本地运行产物；Git 不收录缓存、报告、日志或备份。视频实体放在外部目录：

- 下载区：`C:\Users\Chris\Downloads`
- 视频库：`D:\Private\Videos`

## 数据分区

下载区和视频库使用相同的 8 个分组目录：

- `01_0-2MiB`
- `02_2-4MiB`
- `03_4-6MiB`
- `04_6-8MiB`
- `05_8-12MiB`
- `06_12-16MiB`
- `07_16-32MiB`
- `08_32MiB-plus`

两者映射定义在 `config/video_processor.json`。`size_range_kb` 的单位为 KiB；沿用向上取整到 KiB 后判断左闭右开区间的规则。

## 核心模块

`scripts/run_similarity.py`

- 常规检测和 Web 服务的脚本入口；另有索引重建和离线目录迁移脚本。
- 支持相似度扫描、增量扫描、缓存统计、孤立缓存清理和 Web 服务启动。
- 默认读取 `config/video_processor.json` 中的扫描目录、缓存目录、输出目录和相似检测参数。
- 不再支持旧的 `operation.md --prune` 删除流程。

`utils/video_similarity/checker.py`

- 协调视频扫描、特征提取、缓存读取和相似度计算。
- 支持增量模式：新增视频只与已有库对比，避免全库两两比较。

`utils/video_similarity/extractor.py`

- 使用 OpenCV 抽取采样帧。
- 计算 pHash、dHash、颜色直方图、时长、分辨率等特征。

`utils/video_similarity/cache.py`

- 将视频特征写入 `config/video_processor.json` 中配置的 `cache_dir`。
- JSON 文件名由绝对路径的 MD5 前 16 位生成，内容保存严格 v2 格式、提取参数和完整 SHA-256。
- SQLite 索引根据文件身份及内容摘要支持改名、移动、复制后的特征复用，不保留旧格式转换逻辑。
- 无用缓存检查先筛选候选大小，再检查跨路径引用，避免读取整库特征。详见 [缓存复用说明](CACHE_REUSE.md)。

`utils/video_similarity/reporter.py`

- 生成 Web 所需的 `data.json` 和 `index.html`。
- 旧版 `operation.md` 决策文件已移除。

`utils/video_similarity/server.py`

- 本地 HTTP 服务。
- 支持视频流式预览、相似对忽略、移入 Windows 回收站、资源管理器打开。
- 支持相似比对后台任务：下载区增量比对、视频库全量重新扫描。
- 支持无用特征缓存数量／空间统计和删除；检查不创建任务历史。
- 支持任务历史清空，不修改视频、缓存、报告或忽略决定。
- 支持下载整理 API：状态汇总、按大小分类、按创建时间规范命名、迁移入库并写入特征缓存。
- 支持视频库概览 API：规格数量、容量占比、大小分布。

## 当前数据流

日常流程为：下载根目录 → 按大小分组并按创建时间重命名 → 下载区与视频库比对 → 相似审阅 → 将下载区保留的视频移动到视频库。

比对时读取或计算特征缓存，生成 `data.json` 供双播放器审阅；删除视频会更新当前相似组，忽略决定另存到 `dismissed.json`。移动入库时优先复用原特征并写入新路径缓存。维护页的库内比对只比较视频库内部的视频。


## 运行产物

`cache/video_similarity`

- 保存严格 v2 特征 JSON，以及 `content-index.sqlite3` 和运行时 WAL/SHM 文件。
- 可删除后重建，但重建会显著增加下次扫描耗时。

`output/video_similarity`

- `data.json`：Web 相似对数据。
- `index.html`：Web 工作台页面。
- `dismissed.json`：已忽略的相似对。
- `tasks.json`：最近 20 次后台任务及完整结果；清空记录后持久化为空。
- `server.log`：服务端异常日志。

`logs`

- 历史运行日志。
- 不参与当前主流程判定。

## 风险边界

- Web 审阅中的移除操作将视频放入 Windows 回收站；失败不会自动降级为永久删除。
- Web `按大小分组并重命名` 会移动下载根目录中的视频并修改文件名。
- Web `按创建时间重命名` 会重命名已分类目录中的视频。
- Web `移动到视频库` 会移动视频到视频库，并写入特征缓存。
- Web `删除无用缓存` 只删除特征缓存文件，不删除视频文件。
- 分类、比对、移动和缓存写操作统一为后台任务，接口返回 HTTP 202 和任务 ID；GET /api/tasks 查询摘要，GET /api/tasks/<id> 获取完整结果。任务记录原子保存到 output/video_similarity/tasks.json。
- 同一时间只允许一个后台任务运行；审阅写操作与任务启动共享互斥锁，避免跨标签页并发修改文件。
- 服务重启后未完成任务标记为 interrupted，不自动重跑；浏览器刷新不会中断运行中的任务。
- 重新比对会替换当前审阅列表；首页显示当前待审阅数量，扫描时的历史数量保留在详情。
- 视频库内部比对会按 `n * (n - 1) / 2` 生成比对任务，视频库较大时耗时明显。

## 工作台前端与启动

- `templates/report_template.html`：页面结构。
- `assets/workspace.css`：响应式样式。
- `assets/workspace.js`：连接恢复、后台任务、目录统计和审阅流程。
- `assets/player.js`：双播放器同步、音量记忆、单击播放与双击全屏。
- `assets/artplayer.js`：本地固定版本的播放器，运行时不依赖 CDN。
- `assets/compare-metrics.js`：精确时长、大小及分辨率比较。
- `assets/library-charts.js`：8 组数量／容量分布、对数区间直方图和累计占比。
- `assets/chart.umd.min.js`：本地 Chart.js 4.5.1。
- `tasks.py`：任务互斥、进度、持久化历史和清空。
- `recycle.py`：Windows 回收站适配。
- `scripts/start_web.ps1`：检测现有服务、后台启动并等待就绪；`start_web.bat` 为双击入口。

本地服务绑定 `127.0.0.1:8000`。新安装自动初始化空报告。页面样式和脚本直接由源码 assets 目录提供。可通过 `VIDEO_PROCESSOR_CONFIG` 指定隔离测试配置，默认仍使用原统一配置文件。

## 维护 API

| 接口 | 行为 |
| --- | --- |
| `GET /api/tasks` | 返回任务摘要、运行中的任务 ID 和当前相似组数量 |
| `GET /api/tasks/<id>` | 读取完整任务结果，历史数量不随审阅改变 |
| `POST /api/tasks/clear` | 清空持久化任务历史；有任务运行时返回 409 |
| `GET /api/cache/orphans/status` | 只检查无用缓存，返回数量、字节数、检查时间和错误数量；有任务运行时返回 409 |
| `POST /api/cache/orphans` | 提交缓存检查或删除任务；`dry_run` 默认为 true |

前端进入维护页或相关任务完成后刷新缓存统计，也支持手动刷新；并发刷新共用一次请求。检查失败保留上次显示值并注明失败，不将未知数量显示为零。视频、缓存、索引和任务行为的隔离测试命令见 [工作台说明](WEB_WORKSPACE_V2.md#部署和验证)。
