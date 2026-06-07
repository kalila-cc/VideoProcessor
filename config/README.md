# 配置说明

当前项目只维护一个运行配置文件：

`config/video_processor.json`

它同时定义下载整理、视频库规格映射、相似检测参数、缓存目录、报告输出目录和日志目录。

## 关键字段

- `download_dir`：下载目录，当前为 `C:\Users\Chris\Downloads`。
- `archive_base_dir`：最终视频库根目录，当前为 `D:\Private\Videos`。
- `categories`：规格分区、大小范围和视频库子目录映射。
- `video_extensions`：下载整理和相似检测识别的视频扩展名。
- `cache_dir`：视频特征缓存目录。
- `output_dir`：Web 报告输出目录。
- `log_dir`：运行日志目录。
- `base_dirs`：可选。为空时会根据 `archive_base_dir` 和 `categories` 自动生成视频库扫描目录。
- `incremental_dirs`：可选。用于相似检测增量扫描的新视频目录。
- `similarity`：相似检测采样、权重和阈值参数。

## 路径规则

绝对路径会按原样使用；相对路径会从项目根目录 `D:\Projects\DownloadVideoProcessor` 解析。

因此：

- `cache/video_similarity` 等价于 `D:\Projects\DownloadVideoProcessor\cache\video_similarity`
- `output/video_similarity` 等价于 `D:\Projects\DownloadVideoProcessor\output\video_similarity`

## 修改路径时

如果以后修改下载目录或视频库目录，只需要改 `config/video_processor.json`，不需要再同步多个配置文件。
