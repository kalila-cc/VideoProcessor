import http.server
import socketserver
import json
import os
import sys
import shutil
import subprocess
import logging
import traceback
import hashlib
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from .config import PROJECT_ROOT, load_processor_config, resolve_project_path

class SimilarityReportHandler(http.server.SimpleHTTPRequestHandler):
    """
    Custom handler to serve the similarity report and handle pruning API calls.
    Supports serving absolute paths via /stream/<path>
    """
    _SESSION_DATA = []  # 会话期间过滤后的活跃数据
    _DISMISSED_FILE = None  # dismissed.json 文件路径
    _DISMISSED_PAIRS = {}  # 已忽略的视频对 {pair_id: {...}}

    def __init__(self, *args, directory=None, **kwargs):
        self.base_dir = Path(directory).resolve() if directory else Path.cwd()
        super().__init__(*args, directory=str(self.base_dir), **kwargs)

    def translate_path(self, path):
        """
        Translate URL path to local filesystem path.
        Overrides default behavior to support absolute path streaming.
        """
        # Virtual path for streaming absolute files
        if path.startswith('/stream/'):
            # URL format: /stream/D%3A/Videos/My%20Video.mp4
            # unquote decodes %3A to :, %20 to space, etc.
            decoded_path = unquote(path[8:]) # Strip '/stream/'
            
            # Security: In a multi-user env this is dangerous. 
            # In this local tool context, it's the intended feature.
            # We assume the user has access to the files they are scanning.
            return decoded_path
            
        # Default behavior: relative to served directory
        return super().translate_path(path)

    def do_POST(self):
        """Handle API requests (e.g., pruning files)."""
        if self.path == '/api/prune':
            self.handle_prune()
        elif self.path == '/api/open-explorer':
            self.handle_open_explorer()
        elif self.path == '/api/dismiss':
            self.handle_dismiss()
        elif self.path == '/api/download-library/classify':
            self.handle_download_library_classify()
        elif self.path == '/api/download-library/rename':
            self.handle_download_library_rename()
        elif self.path == '/api/download-library/migrate':
            self.handle_download_library_migrate()
        else:
            self.send_error(404, "Endpoint not found")

    def do_GET(self):
        """Handle GET requests including API endpoints."""
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.path)
        
        # 单个视频对 API: /api/pair?index=0
        if parsed.path == '/api/pair':
            self.handle_pair_api(parse_qs(parsed.query))
            return
        
        # 元数据 API: /api/metadata
        if parsed.path == '/api/metadata':
            self.handle_metadata_api()
            return
        
        # 分页 API: /api/groups?page=1&pageSize=10
        if parsed.path == '/api/groups':
            self.handle_groups_api(parse_qs(parsed.query))
            return

        if parsed.path == '/api/download-library/status':
            self.handle_download_library_status()
            return

        if parsed.path == '/api/video-library/status':
            self.handle_video_library_status()
            return
            
        # 视频流式传输：支持 Range 请求 (拖拽进度条)
        if parsed.path.startswith('/stream/'):
            file_path = self.translate_path(parsed.path)
            self.handle_range_stream(file_path)
            return
            
        # 默认静态文件服务
        try:
            super().do_GET()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        except Exception as e:
            self.log_exception_stack("GET Request Error", e)

    def end_headers(self):
        """添加禁用缓存的响应头"""
        if self.path == '/' or self.path == '/index.html':
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def handle_range_stream(self, file_path):
        """处理 HTTP Range 请求以支持视频拖动进度条"""
        import re
        import mimetypes

        if not os.path.exists(file_path):
            self.send_error(404, "File not found")
            return

        file_size = os.path.getsize(file_path)
        range_header = self.headers.get('Range')

        # 默认返回整个文件
        start = 0
        end = file_size - 1

        if range_header:
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))
                
                # 响应 206 Partial Content
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Content-Length', str(end - start + 1))
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(file_size))
        else:
            self.send_response(200)
            self.send_header('Content-Length', str(file_size))

        self.send_header('Accept-Ranges', 'bytes')
        
        # 自动推断 Content-Type
        ctype, _ = mimetypes.guess_type(file_path)
        self.send_header('Content-Type', ctype or 'video/mp4')
        self.end_headers()

        # 流式读取并发送
        try:
            with open(file_path, 'rb') as f:
                f.seek(start)
                remaining = end - start + 1
                chunk_size = 256 * 1024 # 256KB chunks
                while remaining > 0:
                    read_size = min(remaining, chunk_size)
                    data = f.read(read_size)
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            # 客户端（浏览器）经常在拖动时主动切断旧连接
            pass
        except Exception as e:
            self.log_exception_stack("Streaming error", e)
    
    def handle_groups_api(self, query_params):
        """
        处理分页查询请求
        返回格式: { groups: [...], total, page, pageSize, totalPages }
        """
        try:
            all_groups = self._SESSION_DATA
            
            # 解析分页参数
            page = int(query_params.get('page', ['1'])[0])
            page_size = int(query_params.get('pageSize', ['10'])[0])
            
            # 限制范围
            page = max(1, page)
            page_size = max(1, min(50, page_size))  # 最大 50 条每页
            
            total = len(all_groups)
            total_pages = (total + page_size - 1) // page_size
            
            # 切片获取当前页数据
            start = (page - 1) * page_size
            end = start + page_size
            groups = all_groups[start:end]
            
            response = {
                'groups': groups,
                'total': total,
                'page': page,
                'pageSize': page_size,
                'totalPages': total_pages
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def send_json_response(self, data, status=200):
        """发送 JSON 响应，并增加连接中断保护"""
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            # 客户端（浏览器）可能在收到完整响应前关闭了连接
            pass
        except Exception as e:
            self.log_exception_stack("JSON Response Error", e)

    def log_exception_stack(self, message, exception=None):
        """记录详细的错误日志，包含堆栈信息和请求上下文，重命名以避免冲突"""
        log_msg = f"[{self.path}] {message}"
        if exception:
            log_msg += f": {str(exception)}"
        logging.error(log_msg)
        if exception and not isinstance(exception, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            logging.error(traceback.format_exc())

    @classmethod
    def _project_root(cls):
        return PROJECT_ROOT

    @classmethod
    def _load_download_library_config(cls):
        root = cls._project_root()
        data = load_processor_config()

        categories = []
        for name, item in data.get('categories', {}).items():
            size_range = item.get('size_range_kb') or [0, None]
            categories.append({
                'name': name,
                'min_kb': size_range[0] if len(size_range) > 0 else 0,
                'max_kb': size_range[1] if len(size_range) > 1 else None,
                'archive_subdir': item.get('archive_subdir', name),
            })

        extensions = [ext.lower() for ext in data.get('video_extensions', [])]
        return {
            'project_root': root,
            'download_dir': resolve_project_path(data['download_dir']),
            'archive_base': resolve_project_path(data['archive_base_dir']),
            'extensions': extensions,
            'categories': categories,
            'cache_dir': resolve_project_path(data['cache_dir']),
        }

    @staticmethod
    def _is_video_file(path, extensions):
        return path.is_file() and path.suffix.lower() in extensions

    @classmethod
    def _scan_direct_videos(cls, directory, extensions):
        directory = Path(directory)
        if not directory.exists() or not directory.is_dir():
            return []
        return sorted(
            [item for item in directory.iterdir() if cls._is_video_file(item, extensions)],
            key=lambda p: p.name.lower()
        )

    @classmethod
    def _scan_recursive_videos(cls, directory, extensions):
        directory = Path(directory)
        if not directory.exists() or not directory.is_dir():
            return []
        return sorted(
            [item for item in directory.rglob('*') if cls._is_video_file(item, extensions)],
            key=lambda p: str(p).lower()
        )

    @staticmethod
    def _size_summary(files):
        total_bytes = 0
        for item in files:
            try:
                total_bytes += item.stat().st_size
            except OSError:
                pass
        return {
            'count': len(files),
            'total_bytes': total_bytes,
            'total_mb': round(total_bytes / (1024 * 1024), 2),
        }

    @staticmethod
    def _category_label(category):
        min_kb = category['min_kb']
        max_kb = category['max_kb']
        if max_kb is None:
            return f"{min_kb // 1000}MB+"
        return f"{min_kb // 1000}-{max_kb // 1000}MB"

    @staticmethod
    def _category_for_size(size_kb, categories):
        for category in categories:
            min_kb = category['min_kb']
            max_kb = category['max_kb']
            if size_kb >= min_kb and (max_kb is None or size_kb < max_kb):
                return category
        return categories[-1] if categories else None

    @staticmethod
    def _unique_target_path(target_dir, file_name):
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = target_dir / file_name
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            next_candidate = target_dir / f"{stem}_{counter}{suffix}"
            if not next_candidate.exists():
                return next_candidate
            counter += 1

    @staticmethod
    def _is_standard_video_name(path):
        return re.fullmatch(r'\d{17}(?:_\d+)?', Path(path).stem) is not None

    @staticmethod
    def _collect_file_names(paths):
        names = set()
        for path in paths:
            path = Path(path)
            if path.is_file():
                names.add(path.name.lower())
            elif path.is_dir():
                try:
                    for file_path in path.rglob('*'):
                        if file_path.is_file():
                            names.add(file_path.name.lower())
                except OSError:
                    pass
        return names

    @staticmethod
    def _timestamp_filename(file_path, used_names):
        creation_time = datetime.fromtimestamp(os.path.getctime(file_path))
        ext = file_path.suffix.lower()
        base_millisecond = int(creation_time.microsecond / 1000)

        for ms_offset in range(1000):
            current_ms = (base_millisecond + ms_offset) % 1000
            base = creation_time.strftime('%Y%m%d%H%M%S') + f'{current_ms:03d}'
            candidate = f'{base}{ext}'
            if candidate.lower() not in used_names:
                return candidate

        base = creation_time.strftime('%Y%m%d%H%M%S') + f'{base_millisecond:03d}'
        for suffix_num in range(1, 1000):
            candidate = f'{base}_{suffix_num}{ext}'
            if candidate.lower() not in used_names:
                return candidate

        raise RuntimeError(f"无法为文件生成唯一规范名称: {file_path}")

    def _normalize_download_category_names(self, cfg, selected_by_category=None):
        records = []
        errors = []
        renamed_count = 0
        skipped_count = 0
        scanned_count = 0
        download_dir = cfg['download_dir']
        archive_base = cfg['archive_base']

        for category in cfg['categories']:
            category_name = category['name']
            source_dir = download_dir / category_name
            archive_dir = archive_base / category['archive_subdir']

            if selected_by_category is None:
                files = self._scan_direct_videos(source_dir, cfg['extensions'])
            else:
                files = [
                    Path(item) for item in selected_by_category.get(category_name, [])
                    if Path(item).exists() and Path(item).parent.resolve() == source_dir.resolve()
                ]

            if not files:
                continue

            source_names = self._collect_file_names([source_dir])
            archive_names = self._collect_file_names([archive_dir])
            used_names = source_names | archive_names

            for source in sorted(files, key=lambda p: p.name.lower()):
                scanned_count += 1
                try:
                    current_name = source.name.lower()
                    archive_collision = current_name in archive_names
                    if self._is_standard_video_name(source) and not archive_collision:
                        skipped_count += 1
                        continue

                    new_name = self._timestamp_filename(source, used_names)
                    target_path = source.with_name(new_name)
                    shutil.move(str(source), str(target_path))
                    used_names.discard(current_name)
                    used_names.add(new_name.lower())
                    source_names.discard(current_name)
                    source_names.add(new_name.lower())
                    renamed_count += 1
                    records.append({
                        'action': '规范命名',
                        'file': source.name,
                        'from': str(source),
                        'to': str(target_path),
                        'category': category_name,
                    })
                except Exception as e:
                    errors.append({
                        'file': str(source),
                        'stage': 'rename',
                        'error': str(e),
                    })

        return {
            'scanned_count': scanned_count,
            'renamed_count': renamed_count,
            'skipped_count': skipped_count,
            'errors': errors,
            'records': records,
        }

    def _build_download_library_status(self):
        cfg = self._load_download_library_config()
        download_dir = cfg['download_dir']
        archive_base = cfg['archive_base']
        extensions = cfg['extensions']

        uncategorized_files = self._scan_direct_videos(download_dir, extensions)
        uncategorized_summary = self._size_summary(uncategorized_files)

        category_rows = []
        classified_count = 0
        classified_bytes = 0
        archive_count = 0
        archive_bytes = 0

        for category in cfg['categories']:
            download_category_dir = download_dir / category['name']
            archive_dir = archive_base / category['archive_subdir']
            download_files = self._scan_direct_videos(download_category_dir, extensions)
            archive_files = self._scan_direct_videos(archive_dir, extensions)
            download_summary = self._size_summary(download_files)
            archive_summary = self._size_summary(archive_files)

            classified_count += download_summary['count']
            classified_bytes += download_summary['total_bytes']
            archive_count += archive_summary['count']
            archive_bytes += archive_summary['total_bytes']

            category_rows.append({
                'name': category['name'],
                'label': self._category_label(category),
                'download_dir': str(download_category_dir),
                'archive_dir': str(archive_dir),
                'archive_subdir': category['archive_subdir'],
                'count': download_summary['count'],
                'total_bytes': download_summary['total_bytes'],
                'total_mb': download_summary['total_mb'],
                'archive_count': archive_summary['count'],
                'archive_total_mb': archive_summary['total_mb'],
                'sample_files': [p.name for p in download_files[:5]],
            })

        try:
            from .cache import FeatureCache
            cache_stats = FeatureCache(str(cfg['cache_dir'])).get_cache_stats()
        except Exception as e:
            cache_stats = {'count': 0, 'total_size_mb': 0, 'cache_dir': str(cfg['cache_dir']), 'error': str(e)}

        return {
            'success': True,
            'config': {
                'download_dir': str(download_dir),
                'archive_base': str(archive_base),
                'cache_dir': str(cfg['cache_dir']),
                'video_extensions': extensions,
            },
            'totals': {
                'uncategorized_count': uncategorized_summary['count'],
                'uncategorized_mb': uncategorized_summary['total_mb'],
                'classified_count': classified_count,
                'classified_mb': round(classified_bytes / (1024 * 1024), 2),
                'download_total_count': uncategorized_summary['count'] + classified_count,
                'download_total_mb': round((uncategorized_summary['total_bytes'] + classified_bytes) / (1024 * 1024), 2),
                'archive_count': archive_count,
                'archive_mb': round(archive_bytes / (1024 * 1024), 2),
                'cache_count': cache_stats.get('count', 0),
                'cache_mb': cache_stats.get('total_size_mb', 0),
            },
            'uncategorized': {
                **uncategorized_summary,
                'sample_files': [p.name for p in uncategorized_files[:8]],
            },
            'categories': category_rows,
        }

    def handle_download_library_status(self):
        try:
            self.send_json_response(self._build_download_library_status())
        except Exception as e:
            self.log_exception_stack("Download library status error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_download_library_classify(self):
        try:
            cfg = self._load_download_library_config()
            download_dir = cfg['download_dir']
            files = self._scan_direct_videos(download_dir, cfg['extensions'])
            records = []
            errors = []
            moved_by_category = {}

            for source in files:
                try:
                    size_bytes = source.stat().st_size
                    size_kb = math.ceil(size_bytes / 1024)
                    category = self._category_for_size(size_kb, cfg['categories'])
                    if not category:
                        raise RuntimeError("No category matched")

                    target_dir = download_dir / category['name']
                    target_path = self._unique_target_path(target_dir, source.name)
                    shutil.move(str(source), str(target_path))
                    moved_by_category.setdefault(category['name'], []).append(target_path)
                    records.append({
                        'action': '分类移动',
                        'file': source.name,
                        'from': str(source),
                        'to': str(target_path),
                        'category': category['name'],
                        'size_mb': round(size_bytes / (1024 * 1024), 2),
                    })
                except Exception as e:
                    errors.append({'file': str(source), 'error': str(e)})

            rename_result = self._normalize_download_category_names(cfg, moved_by_category)
            errors.extend(rename_result['errors'])
            records.extend(rename_result['records'])

            response = {
                'success': len(errors) == 0,
                'moved_count': len([r for r in records if r.get('action') == '分类移动']),
                'classified_count': len([r for r in records if r.get('action') == '分类移动']),
                'renamed_count': rename_result['renamed_count'],
                'skipped_count': rename_result['skipped_count'],
                'errors': errors,
                'records': records[:100],
                'status': self._build_download_library_status(),
            }
            self.send_json_response(response)
        except Exception as e:
            self.log_exception_stack("Download library classify error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_download_library_rename(self):
        try:
            cfg = self._load_download_library_config()
            result = self._normalize_download_category_names(cfg)
            response = {
                'success': len(result['errors']) == 0,
                'scanned_count': result['scanned_count'],
                'renamed_count': result['renamed_count'],
                'skipped_count': result['skipped_count'],
                'errors': result['errors'],
                'records': result['records'][:100],
                'status': self._build_download_library_status(),
            }
            self.send_json_response(response)
        except Exception as e:
            self.log_exception_stack("Download library rename error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_download_library_migrate(self):
        try:
            cfg = self._load_download_library_config()
            download_dir = cfg['download_dir']
            archive_base = cfg['archive_base']
            records = []
            errors = []
            cached_count = 0

            from .cache import FeatureCache
            from .config import SimilarityConfig
            from .extractor import VideoFeatureExtractor

            sim_config = SimilarityConfig()
            sim_config.cache_dir = str(cfg['cache_dir'])
            feature_cache = FeatureCache(str(cfg['cache_dir']))
            extractor = VideoFeatureExtractor(sim_config, feature_cache)

            rename_result = self._normalize_download_category_names(cfg)
            records.extend(rename_result['records'])
            errors.extend(rename_result['errors'])

            for category in cfg['categories']:
                source_dir = download_dir / category['name']
                target_dir = archive_base / category['archive_subdir']
                files = self._scan_direct_videos(source_dir, cfg['extensions'])

                for source in files:
                    record = {
                        'action': '迁移入库',
                        'file': source.name,
                        'category': category['name'],
                        'from': str(source),
                    }
                    try:
                        size_bytes = source.stat().st_size
                        target_path = self._unique_target_path(target_dir, source.name)
                        shutil.move(str(source), str(target_path))
                        record['to'] = str(target_path)
                        record['size_mb'] = round(size_bytes / (1024 * 1024), 2)

                        try:
                            extractor.extract(str(target_path), use_cache=True, verbose=False)
                            record['cached'] = True
                            cached_count += 1
                        except Exception as cache_error:
                            record['cached'] = False
                            record['cache_error'] = str(cache_error)
                            errors.append({'file': str(target_path), 'stage': 'cache', 'error': str(cache_error)})

                        records.append(record)
                    except Exception as e:
                        record['error'] = str(e)
                        errors.append({'file': str(source), 'stage': 'move', 'error': str(e)})
                        records.append(record)

            response = {
                'success': len([e for e in errors if e.get('stage') in ('move', 'rename')]) == 0,
                'renamed_count': rename_result['renamed_count'],
                'skipped_count': rename_result['skipped_count'],
                'migrated_count': len([r for r in records if r.get('action') == '迁移入库' and r.get('to')]),
                'cached_count': cached_count,
                'errors': errors,
                'records': records[:100],
                'status': self._build_download_library_status(),
            }
            self.send_json_response(response)
        except Exception as e:
            self.log_exception_stack("Download library migrate error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    @staticmethod
    def _log_size_bucket(size_bytes):
        if size_bytes <= 0:
            return {
                'bucket': -1,
                'label': '0 B',
                'min_bytes': 0,
                'max_bytes': 0,
            }

        size_mb = size_bytes / (1024 * 1024)
        if size_mb < 1:
            return {
                'bucket': -1,
                'label': '<1 MB',
                'min_bytes': 0,
                'max_bytes': 1024 * 1024,
            }

        exponent = int(math.floor(math.log(size_mb, 2)))
        min_mb = 2 ** exponent
        max_mb = 2 ** (exponent + 1)
        return {
            'bucket': exponent,
            'label': f'{min_mb:g}-{max_mb:g} MB' if max_mb < 1024 else f'{min_mb / 1024:g}-{max_mb / 1024:g} GB',
            'min_bytes': int(min_mb * 1024 * 1024),
            'max_bytes': int(max_mb * 1024 * 1024),
        }

    def _build_video_library_status(self):
        cfg = self._load_download_library_config()
        archive_base = cfg['archive_base']
        extensions = cfg['extensions']
        categories = []
        all_sizes = []
        total_count = 0
        total_bytes = 0
        largest = None

        for category in cfg['categories']:
            archive_dir = archive_base / category['archive_subdir']
            files = self._scan_recursive_videos(archive_dir, extensions)
            file_sizes = []
            category_largest = None

            for file_path in files:
                try:
                    size_bytes = file_path.stat().st_size
                except OSError:
                    continue

                file_sizes.append(size_bytes)
                all_sizes.append(size_bytes)
                total_count += 1
                total_bytes += size_bytes

                file_info = {'name': file_path.name, 'path': str(file_path), 'size_bytes': size_bytes}
                if category_largest is None or size_bytes > category_largest['size_bytes']:
                    category_largest = file_info
                if largest is None or size_bytes > largest['size_bytes']:
                    largest = file_info

            category_bytes = sum(file_sizes)
            categories.append({
                'name': category['name'],
                'label': self._category_label(category),
                'archive_subdir': category['archive_subdir'],
                'archive_dir': str(archive_dir),
                'count': len(file_sizes),
                'total_bytes': category_bytes,
                'total_mb': round(category_bytes / (1024 * 1024), 2),
                'average_bytes': round(category_bytes / len(file_sizes)) if file_sizes else 0,
                'min_bytes': min(file_sizes) if file_sizes else 0,
                'max_bytes': max(file_sizes) if file_sizes else 0,
                'largest_file': category_largest,
            })

        histogram_map = {}
        for size_bytes in all_sizes:
            bucket = self._log_size_bucket(size_bytes)
            key = bucket['bucket']
            if key not in histogram_map:
                histogram_map[key] = {
                    **bucket,
                    'count': 0,
                    'total_bytes': 0,
                }
            histogram_map[key]['count'] += 1
            histogram_map[key]['total_bytes'] += size_bytes

        histogram = []
        for key in sorted(histogram_map):
            row = histogram_map[key]
            row['total_mb'] = round(row['total_bytes'] / (1024 * 1024), 2)
            row['count_percent'] = round((row['count'] / total_count) * 100, 2) if total_count else 0
            histogram.append(row)

        for category in categories:
            category['count_percent'] = round((category['count'] / total_count) * 100, 2) if total_count else 0
            category['size_percent'] = round((category['total_bytes'] / total_bytes) * 100, 2) if total_bytes else 0

        try:
            from .cache import FeatureCache
            cache_stats = FeatureCache(str(cfg['cache_dir'])).get_cache_stats()
        except Exception as e:
            cache_stats = {'count': 0, 'total_size_mb': 0, 'cache_dir': str(cfg['cache_dir']), 'error': str(e)}

        return {
            'success': True,
            'config': {
                'archive_base': str(archive_base),
                'cache_dir': str(cfg['cache_dir']),
                'video_extensions': extensions,
            },
            'totals': {
                'count': total_count,
                'total_bytes': total_bytes,
                'total_mb': round(total_bytes / (1024 * 1024), 2),
                'average_bytes': round(total_bytes / total_count) if total_count else 0,
                'largest_file': largest,
                'cache_count': cache_stats.get('count', 0),
                'cache_mb': cache_stats.get('total_size_mb', 0),
            },
            'categories': categories,
            'size_histogram': histogram,
        }

    def handle_video_library_status(self):
        try:
            self.send_json_response(self._build_video_library_status())
        except Exception as e:
            self.log_exception_stack("Video library status error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_pair_api(self, query_params):
        """
        处理单个视频对请求
        返回格式: { pair: {...}, index: 0, total: 100 }
        """
        try:
            all_groups = self._SESSION_DATA
            
            # 解析索引参数
            index = int(query_params.get('index', ['0'])[0])
            print(f"[DEBUG] 请求的 index={index}")
            
            total = len(all_groups)
            if index < 0 or index >= total:
                # 提示信息更加友好
                valid_range = f"0-{total-1}" if total > 0 else "none"
                self.send_json_response({'error': f'Index out of range. Valid range: {valid_range}'}, 400)
                return
            
            pair = all_groups[index]
            
            # 实时检查文件是否存在 (用于状态标志)
            for video in pair.get('videos', []):
                original_path = video.get('originalPath')
                # 检查物理路径是否存在
                video['exists'] = os.path.exists(original_path) if original_path else False

            response = {
                'pair': pair,
                'index': index,
                'total': total
            }
            
            self.send_json_response(response)
            
        except ValueError:
            self.send_json_response({'error': 'Invalid index parameter'}, 400)
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_metadata_api(self):
        """
        处理元数据请求
        返回格式: { total: 100 }
        """
        try:
            response = {
                'total': len(self._SESSION_DATA)
            }
            self.send_json_response(response)
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)


    def handle_prune(self):
        """
        Handle the pruning request.
        Expects a JSON list of ABSOLUTE file paths to delete.
        """
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            files_to_delete = data.get('files', [])
            deleted_count = 0
            errors = []

            print(f"\n[Server] Received prune request for {len(files_to_delete)} files.")

            for file_path in files_to_delete:
                # We expect absolute paths now from the frontend logic
                target_path = Path(file_path).resolve()
                
                try:
                    if not target_path.exists():
                        errors.append(f"File not found: {file_path}")
                        continue
                        
                    # Basic sanity check: Don't delete system files?
                    # Since this is "pruning", maybe we trust the input.
                    
                    if target_path.is_symlink():
                        # If for some reason we still have symlinks
                        os.remove(target_path)
                    else:
                        os.remove(target_path)
                        
                    print(f"[Server] Deleted: {target_path}")
                    deleted_count += 1
                        
                except Exception as e:
                    errors.append(f"Error deleting {file_path}: {str(e)}")

            # Update session state and persist to data.json
            if deleted_count > 0:
                self._update_state_after_prune(files_to_delete)

            # Send response
            response = {
                'success': True,
                'deleted_count': deleted_count,
                'errors': errors
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            self.log_exception_stack("Critical Prune Error", e)
            # 使用 send_json_response 而非 send_error，避免中文编码问题
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_open_explorer(self):
        """Open Windows Explorer and select the specified file."""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            file_path = data.get('path')
            
            if not file_path:
                self.send_json_response({'success': False, 'error': 'No path provided'}, 400)
                return

            target_path = Path(file_path).resolve()
            if not target_path.exists():
                self.send_json_response({'success': False, 'error': 'File not found'}, 404)
                return

            # Windows command to open explorer and select file
            # explorer /select,"C:\path\to\file"
            print(f"[Server] Opening explorer for: {target_path}")
            subprocess.run(['explorer', '/select,', str(target_path)])
            
            self.send_json_response({'success': True})
        except Exception as e:
            self.log_exception_stack("Open Explorer Error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def _update_state_after_prune(self, deleted_paths=None):
        """
        根据删除的文件路径同步更新内存数据和 data.json。
        
        Args:
            deleted_paths: 刚刚被删除的文件路径列表。如果提供，将使用内存过滤（快）；
                           如果不提供，将扫描磁盘（慢）。
        """
        if deleted_paths:
            # 性能优化：直接从内存排除包含这些路径的组
            print(f"[Server] Memory-based state sync for {len(deleted_paths)} paths...")
            deleted_set = {str(Path(p).resolve()) for p in deleted_paths}
            
            raw_data = self._SESSION_DATA
            new_data = []
            removed_count = 0
            
            for pair in raw_data:
                # 检查该对中是否有任何视频在已删除列表里
                has_deleted = False
                for video in pair.get('videos', []):
                    # 统一转为绝对路径进行比对
                    orig_path = str(Path(video.get('originalPath', '')).resolve())
                    if orig_path in deleted_set:
                        has_deleted = True
                        break
                
                if not has_deleted:
                    new_data.append(pair)
                else:
                    removed_count += 1
        else:
            # 回退方案：全量扫盘（慢）
            print(f"[Server] Disk-based state sync (Scanning all files)...")
            raw_data = self._SESSION_DATA
            new_data = []
            removed_count = 0
            for pair in raw_data:
                all_exist = True
                for video in pair.get('videos', []):
                    original_path = video.get('originalPath')
                    if not original_path or not os.path.exists(original_path):
                        all_exist = False
                        break
                if all_exist: new_data.append(pair)
                else: removed_count += 1
        
        # 更新内存
        SimilarityReportHandler._SESSION_DATA = new_data
        
        # 更新磁盘 data.json
        data_file = Path(self.base_dir) / "data.json"
        try:
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            print(f"[Server] State updated. Removed {removed_count} pairs. Remaining: {len(new_data)}")
        except Exception as e:
            print(f"[Server] Error persisting data.json: {e}")

    def handle_dismiss(self):
        """
        处理"均保留"请求 - 将视频对标记为已忽略。
        下次启动时将不再显示该视频对。
        """
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            path_a = data.get('pathA')
            path_b = data.get('pathB')
            
            if not path_a or not path_b:
                self.send_json_response({'success': False, 'error': 'Missing pathA or pathB'}, 400)
                return
            
            # 生成唯一 ID 并保存
            pair_id = self._generate_pair_id(path_a, path_b)
            self._save_dismissed_pair(pair_id, path_a, path_b)
            
            # 从内存中移除该视频对
            self._remove_pair_from_session(path_a, path_b)
            
            print(f"[Server] Dismissed pair: {pair_id[:8]}...")
            self.send_json_response({'success': True, 'pairId': pair_id})
            
        except Exception as e:
            self.log_exception_stack("Dismiss API Error", e)
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    @staticmethod
    def _generate_pair_id(path_a: str, path_b: str) -> str:
        """
        基于两个视频路径生成唯一标识符。
        排序确保 (A, B) 和 (B, A) 生成相同的 ID。
        """
        paths = sorted([str(Path(path_a).resolve()), str(Path(path_b).resolve())])
        combined = "|".join(paths)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]

    @classmethod
    def _load_dismissed_pairs(cls, dismissed_file: Path) -> dict:
        """加载已忽略的视频对缓存"""
        cls._DISMISSED_FILE = dismissed_file
        if dismissed_file.exists():
            try:
                with open(dismissed_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cls._DISMISSED_PAIRS = data.get('dismissed', {})
                    return cls._DISMISSED_PAIRS
            except Exception as e:
                logging.error(f"Error loading dismissed.json: {e}")
        cls._DISMISSED_PAIRS = {}
        return cls._DISMISSED_PAIRS

    @classmethod
    def _save_dismissed_pair(cls, pair_id: str, path_a: str, path_b: str):
        """保存忽略的视频对到缓存文件"""
        cls._DISMISSED_PAIRS[pair_id] = {
            'paths': sorted([str(Path(path_a).resolve()), str(Path(path_b).resolve())]),
            'dismissed_at': datetime.now().isoformat()
        }
        
        if cls._DISMISSED_FILE:
            try:
                cache_data = {
                    'version': 1,
                    'dismissed': cls._DISMISSED_PAIRS
                }
                with open(cls._DISMISSED_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logging.error(f"Error saving dismissed.json: {e}")

    @classmethod
    def _remove_pair_from_session(cls, path_a: str, path_b: str):
        """从会话数据中移除指定的视频对"""
        path_a_resolved = str(Path(path_a).resolve())
        path_b_resolved = str(Path(path_b).resolve())
        
        new_data = []
        for pair in cls._SESSION_DATA:
            videos = pair.get('videos', [])
            if len(videos) >= 2:
                pair_paths = {str(Path(v.get('originalPath', '')).resolve()) for v in videos}
                if path_a_resolved in pair_paths and path_b_resolved in pair_paths:
                    continue  # 跳过这个视频对
            new_data.append(pair)
        
        cls._SESSION_DATA = new_data

def run_server(output_dir, port=8000):

    """
    Start the reporting server.
    """
    output_dir = Path(output_dir).resolve()
    
    # 配置日志系统
    log_file = output_dir / "server.log"
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        return

    # 启动前检查必要文件
    data_file = output_dir / "data.json"
    index_file = output_dir / "index.html"
    
    missing = []
    if not data_file.exists(): missing.append("data.json")
    if not index_file.exists(): missing.append("index.html")
    
    if missing:
        print("\n" + "!"*60)
        print(f"错误: 无法启动服务器，缺失必要文件: {', '.join(missing)}")
        print(f"预定目录: {output_dir}")
        print("建议: 请运行一次完整的相似度扫描以生成这些文件。")
        print("!"*60 + "\n")
        return

    # Change to the directory so relative paths work nicely for index.html
    try:
        os.chdir(output_dir)
    except Exception as e:
        print(f"错误: 无法切换到目录 {output_dir}: {e}")
        return
    
    # Load and filter data for the session
    print(f"Loading and validating video similarity data...")
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # 加载已忽略的视频对缓存
        dismissed_file = output_dir / "dismissed.json"
        dismissed_pairs = SimilarityReportHandler._load_dismissed_pairs(dismissed_file)
        dismissed_count = 0
        
        filtered_data = []
        for pair in raw_data:
            # Check if all videos in the pair exist
            all_exist = True
            videos = pair.get('videos', [])
            for video in videos:
                if not os.path.exists(video.get('originalPath', '')):
                    all_exist = False
                    break
            
            if not all_exist:
                continue
            
            # 检查是否已被用户忽略（均保留）
            if len(videos) >= 2:
                path_a = videos[0].get('originalPath', '')
                path_b = videos[1].get('originalPath', '')
                pair_id = SimilarityReportHandler._generate_pair_id(path_a, path_b)
                if pair_id in dismissed_pairs:
                    dismissed_count += 1
                    continue
            
            filtered_data.append(pair)
        
        # Set to class variable
        SimilarityReportHandler._SESSION_DATA = filtered_data
        
        if dismissed_count > 0:
            print(f"[Server] Skipped {dismissed_count} dismissed pairs from cache")
    except Exception as e:
        print(f"Error initializing session data: {e}")
        return


    print(f"\n" + "="*60)
    print(f"Starting Video Similarity Interactive Report")
    print(f"Root Directory: {output_dir}")
    print(f"Server URL:     http://localhost:{port}")
    print(f"Features:       Dynamic Data Loading & Pruning")
    if len(raw_data) > len(filtered_data):
        print(f"Status:         Showing {len(filtered_data)} unresolved out of {len(raw_data)} total pairs")
    print(f"="*60 + "\n")
    print("[Press Ctrl+C to stop the server]")

    # Create server with 'directory' argument to serve files from output_dir
    handler = lambda *args: SimilarityReportHandler(*args, directory=output_dir)
    
    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ThreadedTCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            httpd.server_close()
