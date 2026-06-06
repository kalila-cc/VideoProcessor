# -*- coding: utf-8 -*-
"""Generate the local Web report for video similarity results."""

import json
import re
from pathlib import Path
from typing import List
from urllib.parse import quote


def format_duration(seconds: float) -> str:
    """Format seconds as M:SS for the report UI."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def format_file_size(file_path: str) -> str:
    """Return a compact file size label for a video path."""
    try:
        size = Path(file_path).stat().st_size
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size / (1024 * 1024):.1f}MB"
    except OSError:
        return "N/A"


class VideoSimilarityReporter:
    """Build data.json and index.html for the interactive similarity report."""

    @staticmethod
    def generate_report(similar_pairs: List[dict], base_output_dir: str = "output/video_similarity"):
        """Generate Web report artifacts for similar video pairs."""
        base_path = Path(base_output_dir).resolve()
        base_path.mkdir(parents=True, exist_ok=True)

        report_data = VideoSimilarityReporter._prepare_data(similar_pairs)

        data_file = base_path / "data.json"
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        VideoSimilarityReporter.generate_html_report(report_data, base_path)
        print(f"  详细报告已生成: {base_path}")

    @staticmethod
    def _prepare_data(similar_pairs: List[dict]) -> List[dict]:
        """Convert checker output into the structure consumed by the frontend."""
        report_data = []
        for i, pair in enumerate(similar_pairs, 1):
            group_id = f"G{i:03d}"
            vid_a = pair["video_a"]
            vid_b = pair["video_b"]

            def get_res_score(res_str):
                try:
                    w, h = map(int, res_str.split("x"))
                    return w * h
                except Exception:
                    return 0

            try:
                size_a = Path(vid_a["path"]).stat().st_size
                size_b = Path(vid_b["path"]).stat().st_size
            except OSError:
                size_a = 0
                size_b = 0

            score_a = get_res_score(vid_a["resolution"]) * size_a
            score_b = get_res_score(vid_b["resolution"]) * size_b

            recommend = "equal"
            if score_a > score_b * 1.05:
                recommend = "A"
            elif score_b > score_a * 1.05:
                recommend = "B"

            report_data.append({
                "groupId": group_id,
                "similarity": f"{pair['score']:.1%}",
                "recommend": recommend,
                "videos": [
                    {
                        "id": "A",
                        "name": vid_a["name"],
                        "path": f"/stream/{quote(str(vid_a['path']))}",
                        "originalPath": str(vid_a["path"]),
                        "duration": format_duration(vid_a["duration"]),
                        "resolution": vid_a["resolution"],
                        "size": format_file_size(vid_a["path"]),
                    },
                    {
                        "id": "B",
                        "name": vid_b["name"],
                        "path": f"/stream/{quote(str(vid_b['path']))}",
                        "originalPath": str(vid_b["path"]),
                        "duration": format_duration(vid_b["duration"]),
                        "resolution": vid_b["resolution"],
                        "size": format_file_size(vid_b["path"]),
                    },
                ],
            })
        return report_data

    @staticmethod
    def generate_html_report(report_data: List[dict], output_dir: Path):
        """Generate index.html from the frontend template."""
        html_file = output_dir / "index.html"

        template_path = Path(__file__).parent / "templates" / "report_template.html"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()
        except Exception as e:
            print(f"  错误: 无法加载 HTML 模板: {e}")
            return

        metadata = {"total": len(report_data)}
        json_metadata = json.dumps(metadata, ensure_ascii=False)
        html_content = re.sub(r"\{\s*json_metadata\s*\}", json_metadata, template_content)

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  交互报告: {html_file}")
