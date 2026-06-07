# Scripts

本目录只保留当前项目仍在使用的命令行入口。下载分类、规范命名、迁移入库和相似视频删除已经并入 Web 工作台，不再保留旧的多脚本流水线。

## 脚本清单

| 脚本 | 用途 |
| --- | --- |
| `run_similarity.py` | 相似检测、缓存维护、Web 工作台启动 |

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

已启动 Web 工作台时，可直接在 `视频对比` 页点击 `重新扫描比对`，后台会调用同一脚本刷新报告和当前会话数据。

使用配置文件中的目录：

```powershell
python scripts\run_similarity.py
```

显式传入已有库和新增目录：

```powershell
python scripts\run_similarity.py -d D:\Private\Videos\0_XS(0MB_10MB) D:\Private\Videos\1_S(10MB_20MB) D:\Private\Videos\2_M(20MB_40MB) D:\Private\Videos\3_L(40MB_200MB) D:\Private\Videos\4_XL(200MB_INF) -i C:\Users\Chris\Downloads\XS C:\Users\Chris\Downloads\S C:\Users\Chris\Downloads\M C:\Users\Chris\Downloads\L C:\Users\Chris\Downloads\XL
```

输出：

- `output/video_similarity/data.json`
- `output/video_similarity/index.html`
- `logs/video_similarity/result.log`
- `logs/video_similarity/incremental_result.log`

### 缓存维护

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

旧版 `operation.md` 和 `--prune` 批量删除流程也已移除。现在相似视频清理通过 Web 页面中的 `删除此视频` 执行真实删除。
