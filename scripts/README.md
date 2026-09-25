# Scripts

本目录只保留当前项目仍在使用的命令行入口。下载分类、规范命名、迁移入库和相似视频删除已经并入 Web 工作台，不再保留旧的多脚本流水线。

## 脚本清单

| 脚本 | 用途 |
| --- | --- |
| `run_similarity.py` | 相似检测、缓存维护、Web 工作台启动 |
| `start_web.ps1` | 检测已有服务、后台启动并等待就绪；`-NoBrowser` 不打开浏览器 |
| `rebuild_cache_index.py` | 校验当前格式特征并重建内容索引；`--full-hash` 强制重验完整摘要，不重新解码 |
| `regroup_library.py` | 停服后生成 8 组迁移清单；`--apply --run-dir <清单目录>` 备份并迁移，支持中断续跑 |

## run_similarity.py

### 启动 Web 工作台

推荐从项目根目录执行：

```powershell
cd D:\Projects\DownloadVideoProcessor
python scripts\run_similarity.py --server-only
```

访问：

```text
http://localhost:8000
```

### 执行相似检测

已启动 Web 工作台时，优先使用以下入口：

- `下载整理 → 与视频库比对`，或 `相似审阅 → 下载区与视频库比对`：调用同一脚本执行 `-d 视频库目录 -i 下载分组目录`。
- `维护与记录 → 比对视频库内部重复项`：调用同一脚本只扫描视频库目录，执行全量两两比对。两种比对都会替换当前审阅列表。

使用配置文件中的目录：

```powershell
python scripts\run_similarity.py
```

显式传入已有库和新增目录：

```powershell
python scripts\run_similarity.py -d "D:\Private\Videos" -i "C:\Users\Chris\Downloads\01_0-2MiB"
```

输出：

- `output/video_similarity/data.json`
- `output/video_similarity/index.html`
- `logs/video_similarity/result.log`
- `logs/video_similarity/incremental_result.log`

### 缓存维护

已启动 Web 工作台时，在 `维护与记录` 页查看无用缓存数量和可释放空间，必要时点击 `刷新无用缓存数量`，再使用 `删除无用缓存`。只删除无法对应现存视频且未被复用的缓存，不删除视频文件。`重建缓存索引` 复用当前格式特征；`计算缺失特征` 仅补算失效或缺失记录。

```powershell
python scripts\run_similarity.py --cache-stats
python scripts\run_similarity.py --clean-orphan-cache --dry-run
python scripts\run_similarity.py --clean-orphan-cache
python scripts\run_similarity.py --clear-cache
```

## 已移除入口

- `run_renamer.py`
- `run_mover.py`
- `run_pipeline.py`

旧版 `operation.md` 和 `--prune` 批量删除流程也已移除。现在相似视频清理通过每个视频下方的红色“删除此视频”按钮，将所在侧的视频送入 Windows 回收站。启动入口 start_web.bat 调用本目录 start_web.ps1，在后台启动服务并等待就绪。
