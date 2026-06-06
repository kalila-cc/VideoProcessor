# -*- coding: utf-8 -*-
"""Lightweight package exports for the video processing project.

The original utility package eagerly imported unrelated data-structure helpers.
That made video scripts require optional dependencies such as graphviz before
the video modules could even show --help. Keep video imports cheap and load
legacy helpers only when they are requested directly.
"""

import importlib

__all__ = [
    "video_similarity",
    "ListNode",
    "TreeNode",
    "Emoji",
    "Order",
    "Condition",
    "ArrayTools",
    "TimeTools",
    "LogTools",
]


def __getattr__(name):
    if name == "video_similarity":
        return importlib.import_module(f"{__name__}.{name}")

    if name in {"ListNode", "TreeNode"}:
        from .data_structures import ListNode, TreeNode

        return {"ListNode": ListNode, "TreeNode": TreeNode}[name]

    if name in {"Emoji", "Order", "Condition", "ArrayTools", "TimeTools", "LogTools"}:
        from .common import Emoji, Order, Condition
        from .common import ArrayTools, TimeTools, LogTools

        return {
            "Emoji": Emoji,
            "Order": Order,
            "Condition": Condition,
            "ArrayTools": ArrayTools,
            "TimeTools": TimeTools,
            "LogTools": LogTools,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
