# -*- coding: utf-8 -*-

from typing import Optional, List

class ListNode:
    default_has_head = False

    def __init__(self,
                 val: int = 0,
                 next: Optional['ListNode'] = None,
                 has_head: bool = default_has_head,
                 reverse:bool = False):
        self.val = val
        self.next = next
        self.has_head = has_head
        self.reverse = reverse

    def __repr__(self):
        desc = self.description(sep='->')
        desc = desc if len(desc) > 0 else 'None'
        return f'<ListNode val = {self.val}, list = {desc}>'

    def show(self, sep: str = '->'):
        desc = self.description(sep)
        print(desc)

    def description(self, sep: str = '->', reverse: bool = False) -> str:
        desc: str = ''
        node: Optional[ListNode] = self.next if self.has_head else self
        desc_list = []
        while node:
            desc_list.append(str(node.val))
            node = node.next
        if reverse:
            desc_list.reverse()
        return sep.join(desc_list)

    @classmethod
    def from_list(cls,
                  lst: List[int],
                  reverse: bool = False,
                  has_head: bool = False) -> Optional['ListNode']:
        # 参数验证
        if not isinstance(lst, list) or any(not isinstance(x, int) for x in lst):
            raise ValueError("输入必须为整数列表")

        # 处理反转
        processed_lst = lst[::-1] if reverse else lst

        # 构建链表
        dummy = cls()  # 哨兵节点简化操作
        current = dummy
        for num in processed_lst:
            current.next = cls(num)
            current = current.next

        return dummy if has_head else dummy.next
