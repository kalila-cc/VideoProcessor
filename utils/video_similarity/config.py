# -*- coding: utf-8 -*-
"""Configuration loading for the video processor."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "config" / "video_processor.json"


def resolve_project_path(path_value: str) -> Path:
    """Resolve absolute paths as-is and relative paths from the project root."""
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def load_processor_config(config_path: str = None) -> Dict[str, Any]:
    """Load the single project configuration file."""
    config_file = Path(config_path) if config_path else CONFIG_FILE
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def build_archive_dirs(config_data: Dict[str, Any]) -> List[str]:
    """Derive archive category directories from archive_base_dir and categories."""
    archive_base = resolve_project_path(config_data["archive_base_dir"])
    dirs = []
    for item in config_data.get("categories", {}).values():
        archive_subdir = item.get("archive_subdir")
        if archive_subdir:
            dirs.append(str((archive_base / archive_subdir).resolve()))
    return dirs


@dataclass
class SimilarityConfig:
    """Similarity calculation and runtime configuration."""

    num_sample_frames: int = 15

    weight_duration: float = 0.10
    weight_phash: float = 0.40
    weight_dhash: float = 0.20
    weight_histogram: float = 0.30

    duration_threshold: float = 0.95
    similarity_high: float = 0.90
    similarity_medium: float = 0.80

    hash_size: int = 16
    hist_bins: int = 64
    max_workers: int = None

    output_dir: str = "output/video_similarity"
    cache_dir: str = "cache/video_similarity"
    log_dir: str = "logs"

    base_dirs: List[str] = field(default_factory=list)
    incremental_dirs: List[str] = field(default_factory=list)

    video_extensions: List[str] = field(default_factory=lambda: [
        ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"
    ])

    def __post_init__(self):
        self.load_from_json()

    def load_from_json(self, config_path: str = None):
        """Load similarity settings and runtime paths from config/video_processor.json."""
        try:
            data = load_processor_config(config_path)
        except Exception as e:
            print(f"  [警告] 加载配置文件失败: {e}")
            return

        similarity = data.get("similarity", {})
        for key, value in similarity.items():
            if hasattr(self, key):
                setattr(self, key, value)

        if "video_extensions" in data:
            self.video_extensions = [ext.lower() for ext in data["video_extensions"]]

        if "cache_dir" in data:
            self.cache_dir = str(resolve_project_path(data["cache_dir"]))
        if "output_dir" in data:
            self.output_dir = str(resolve_project_path(data["output_dir"]))
        if "log_dir" in data:
            self.log_dir = str(resolve_project_path(data["log_dir"]))

        configured_base_dirs = data.get("base_dirs") or []
        if configured_base_dirs:
            self.base_dirs = [str(resolve_project_path(path)) for path in configured_base_dirs]
        else:
            self.base_dirs = build_archive_dirs(data)

        self.incremental_dirs = [
            str(resolve_project_path(path)) for path in data.get("incremental_dirs", [])
        ]

    def save_to_json(self, config_path: str = None):
        """Save the current similarity section back into the unified config file."""
        config_file = Path(config_path) if config_path else CONFIG_FILE
        data = load_processor_config(str(config_file)) if config_file.exists() else {}

        data["cache_dir"] = self.cache_dir
        data["output_dir"] = self.output_dir
        data["log_dir"] = self.log_dir
        data["base_dirs"] = self.base_dirs
        data["incremental_dirs"] = self.incremental_dirs
        data["video_extensions"] = self.video_extensions
        data["similarity"] = {
            "num_sample_frames": self.num_sample_frames,
            "weight_duration": self.weight_duration,
            "weight_phash": self.weight_phash,
            "weight_dhash": self.weight_dhash,
            "weight_histogram": self.weight_histogram,
            "duration_threshold": self.duration_threshold,
            "similarity_high": self.similarity_high,
            "similarity_medium": self.similarity_medium,
            "hash_size": self.hash_size,
            "hist_bins": self.hist_bins,
            "max_workers": self.max_workers,
        }

        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
