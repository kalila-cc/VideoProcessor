# -*- coding: utf-8 -*-

from enum import StrEnum

class Emoji(StrEnum):
    """常用 Emoji 符号"""
    lucky = '🍀'
    correct = '✅'
    error = '❌'
    warning = '⚠️'

class Order(StrEnum):
    """排序方向"""
    asc = 'asc'
    desc = 'desc'

class Condition(StrEnum):
    """比较条件"""
    greater = 'greater'
    greater_equal = 'greater_equal'
    equal = 'equal'
    less = 'less'
    less_equal = 'less_equal'
