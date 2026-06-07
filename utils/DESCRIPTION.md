# utils 目录说明

当前视频处理主流程只依赖 `video_similarity`。

```text
utils/
├── video_similarity/    # 相似检测、报告生成、Web 服务和下载整理 API
├── common/              # 从旧项目保留的通用工具
└── data_structures/     # 从旧项目保留的数据结构工具
```

`video_similarity/server.py` 读取 `config/video_processor.json` 来执行下载目录分类、规范命名、迁移入库和特征缓存写入。

旧的 `video_renamer` 模块已经移除；分类、规范命名和迁移能力由 Web 工作台统一提供。
