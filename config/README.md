# 配置说明

## 下载整理配置

`config/download_library.json` 定义下载目录、最终视频库目录、视频规格分区和支持的视频扩展名。

关键字段：

- `download_dir`：下载目录，当前为 `C:\Users\Chris\Downloads`。
- `archive_base_dir`：最终视频库根目录，当前为 `D:\Private\Videos`。
- `categories`：规格分区和目标视频库子目录映射。
- `video_extensions`：下载整理会识别的视频扩展名。

这个配置被 `utils/video_similarity/server.py` 的 Web 下载整理 API 读取。

## 相似检测配置

`utils/video_similarity/config.json` 定义相似检测参数，包括采样帧数、相似度权重、缓存目录、输出目录、已有库目录和增量目录。

常用字段：

- `cache_dir`：特征缓存目录。
- `output_dir`：Web 报告输出目录。
- `base_dirs`：已有视频库目录。
- `incremental_dirs`：新增视频目录。
- `similarity_medium`：相似对输出阈值。

## 路径变更时需要同步

如果以后修改下载目录或视频库目录，需要同步检查：

- `config/download_library.json`
- `utils/video_similarity/config.json` 中的 `base_dirs` 和 `incremental_dirs`
- 文档中的示例命令
