# -*- coding: utf-8 -*-

from typing import List, Any
from .enums import Order, Condition

class ArrayTools:
    """数组/算法工具类"""

    @classmethod
    def binary_search(cls,
                      arr: List[int],
                      target: int,
                      order: Order = Order.asc,
                      condition: Condition = Condition.equal
                      ) -> int:
        left, right = 0, len(arr) - 1
        result = -1
        """
        诀窍：条件满足，异左同右，左增右减
        e.g. 在升序数组(->)中搜索首个大于等于(>=)目标值，方向同向均向右，则在作用域内部变更右指针，右指针更新为中指针-1
        """
        while left <= right:
            # 避免大数运算溢出
            mid = left + (right - left) // 2 # 避免大数运算溢出
            if order == Order.asc:
                if condition == Condition.equal:
                    if arr[mid] == target:
                        result = mid
                        right = mid - 1
                    elif arr[mid] > target:
                        right = mid - 1
                    else:
                        left = mid + 1
                elif condition == Condition.greater:
                    if arr[mid] > target:
                        result = mid
                        right = mid - 1
                    else:
                        left = mid + 1
                elif condition == Condition.greater_equal:
                    if arr[mid] >= target:
                        result = mid
                        right = mid - 1
                    else:
                        left = mid + 1
                elif condition == Condition.less:
                    if arr[mid] < target:
                        result = mid
                        left = mid + 1
                    else:
                        right = mid - 1
                elif condition == Condition.less_equal:
                    if arr[mid] <= target:
                        result = mid
                        left = mid + 1
                    else:
                        right = mid - 1
            else:  # 降序
                if condition == Condition.equal:
                    if arr[mid] == target:
                        result = mid
                        right = mid - 1
                    elif arr[mid] < target:
                        right = mid - 1
                    else:
                        left = mid + 1
                elif condition == Condition.greater:
                    if arr[mid] > target:
                        result = mid
                        left = mid + 1
                    else:
                        right = mid - 1
                elif condition == Condition.greater_equal:
                    if arr[mid] >= target:
                        result = mid
                        left = mid + 1
                    else:
                        right = mid - 1
                elif condition == Condition.less:
                    if arr[mid] < target:
                        result = mid
                        right = mid - 1
                    else:
                        left = mid + 1
                elif condition == Condition.less_equal:
                    if arr[mid] <= target:
                        result = mid
                        right = mid - 1
                    else:
                        left = mid + 1

        return result

    @classmethod
    def show_matrix(cls, matrix: List[List[Any]], end: str = '\n'):
        """打印二维矩阵"""
        for row in matrix:
            print(row)
        if end:
            print(end, end='')
