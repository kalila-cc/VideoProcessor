# -*- coding: utf-8 -*-

import time
from functools import wraps

class TimeTools:
    """时间/性能测量工具类"""

    @staticmethod
    def precise_timer(func):
        """高精度计时装饰器"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            if elapsed < 1:
                elapsed_ms = elapsed * 1000
                output = f"{elapsed_ms:.3f} ms"
            else:
                output = f"{elapsed:.6f} s"
            print(f"Function \"{func.__name__}\" takes {output}")
            return result
        return wrapper
