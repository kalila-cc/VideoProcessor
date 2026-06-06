# 旧流程清理记录

本项目已经从旧的多脚本 CLI 流程收敛到 Web 工作台主流程。

## 已删除

- `scripts/run_renamer.py`
- `scripts/run_mover.py`
- `scripts/run_pipeline.py`
- `scripts/README-run_renamer.md`
- `scripts/README-run_mover.md`
- `scripts/README-run_pipeline.md`
- `utils/video_renamer/`
- `output/video_similarity/operation.md`

## 已移除逻辑

- 手工编辑 `operation.md`。
- `run_mover.py` 读取 `operation.md` 后迁移入库。
- `run_similarity.py --prune` 读取 `operation.md` 后删除未勾选文件。
- `run_pipeline.py` 串联分类、相似检测、人工编辑 `operation.md`、迁移入库。

## 当前替代方式

- 分类：Web `下载整理` 页的 `一键分类`。
- 规范命名：Web `下载整理` 页的 `一键规范命名`。
- 入库和缓存：Web `下载整理` 页的 `一键迁移并缓存`。
- 相似视频删除：Web `视频对比` 页的 `删除此视频`。
- 相似检测：`scripts/run_similarity.py`。

## 当前配置入口

`utils/video_similarity/server.py` 读取 `config/download_library.json`。当前项目主流程不再依赖 `utils/video_renamer`。
