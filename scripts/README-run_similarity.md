# run_similarity.py

`run_similarity.py` 是当前唯一保留的命令行入口，负责相似检测、缓存维护和启动本地 Web 工作台。

## 启动 Web

```powershell
cd D:\Projects\DownloadVideoProcessor\scripts
python run_similarity.py --server-only
```

访问：

```text
http://localhost:8000
```

## 执行相似检测

使用配置文件中的目录：

```powershell
python run_similarity.py
```

显式传入已有库和新增目录：

```powershell
python run_similarity.py -d D:\Private\Videos\0_XS(0MB_10MB) D:\Private\Videos\1_S(10MB_20MB) D:\Private\Videos\2_M(20MB_40MB) D:\Private\Videos\3_L(40MB_200MB) D:\Private\Videos\4_XL(200MB_INF) -i C:\Users\Chris\Downloads\XS C:\Users\Chris\Downloads\S C:\Users\Chris\Downloads\M C:\Users\Chris\Downloads\L C:\Users\Chris\Downloads\XL
```

输出：

- `output/video_similarity/data.json`
- `output/video_similarity/index.html`
- `logs/video_similarity/result.log`
- `logs/video_similarity/incremental_result.log`

## 缓存维护

```powershell
python run_similarity.py --cache-stats
python run_similarity.py --clean-orphan-cache --dry-run
python run_similarity.py --clean-orphan-cache
python run_similarity.py --clear-cache
```

## 已移除参数

`--prune` 已删除。旧版 `operation.md` 勾选后批量删除的流程不再使用；现在相似视频清理通过 Web 页面中的 `删除此视频` 执行真实删除。
