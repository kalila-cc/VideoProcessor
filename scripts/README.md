# Scripts

当前只保留一个脚本入口：

| 脚本 | 用途 |
| --- | --- |
| `run_similarity.py` | 相似检测、缓存维护、Web 工作台启动 |

## 常用命令

启动 Web 工作台：

```powershell
cd D:\Projects\DownloadVideoProcessor\scripts
python run_similarity.py --server-only
```

重新生成相似检测报告：

```powershell
python run_similarity.py
```

查看缓存统计：

```powershell
python run_similarity.py --cache-stats
```

预览孤立缓存清理：

```powershell
python run_similarity.py --clean-orphan-cache --dry-run
```

## 已移除脚本

以下旧入口已删除：

- `run_renamer.py`
- `run_mover.py`
- `run_pipeline.py`

对应功能已经并入 Web 工作台的 `下载整理` 页面和 `视频对比` 页面。
