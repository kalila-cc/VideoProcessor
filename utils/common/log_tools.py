# -*- coding: utf-8 -*-

class LogTools:
    """彩色日志输出工具类"""

    @classmethod
    def info(cls, msg: str | Exception):
        """输出普通信息"""
        msg = msg if type(msg) == str else repr(msg)
        print(msg)

    @classmethod
    def warning(cls, msg: str | Exception):
        """输出警告信息（黄色）"""
        msg = msg if type(msg) == str else repr(msg)
        print(f'\033[33m{msg}\033[0m')

    @classmethod
    def error(cls, msg: str | Exception):
        """输出错误信息（红色）"""
        msg = msg if type(msg) == str else repr(msg)
        print(f'\033[31m{msg}\033[0m')

    @classmethod
    def success(cls, msg: str | Exception):
        """输出成功信息（绿色）"""
        msg = msg if type(msg) == str else repr(msg)
        print(f'\033[32m{msg}\033[0m')
