# -*- coding: utf-8 -*-

from typing import Optional
from graphviz import Digraph

class TreeNode:
    def __init__(self,
                 val: int = 0,
                 left: 'Optional[TreeNode]' = None,
                 right: 'Optional[TreeNode]' = None):
        self.val = val
        self.left = left
        self.right = right

    def __repr__(self):
        return f'<TreeNode val = {self.val}, children = [{self.left.val if self.left else None}, {self.right.val if self.right else None}]>'

    @classmethod
    def from_list(cls, lst):
        """从列表构建二叉树（支持空节点）"""
        if not lst:
            return None
        root = cls(lst[0])
        queue = [root]
        i = 1
        while queue and i < len(lst):
            node = queue.pop(0)
            if i < len(lst) and lst[i] is not None:
                node.left = cls(lst[i])
                queue.append(node.left)
            i += 1
            if i < len(lst) and lst[i] is not None:
                node.right = cls(lst[i])
                queue.append(node.right)
            i += 1
        return root

    def visualize(self, filename="tree", fmt="png"):  # 参数重命名：format → fmt
        """优化后的可视化方法（支持相同值节点）"""
        dot = Digraph(comment='Binary Tree',
                      graph_attr={'ordering': 'out', 'rankdir': 'TB'})
        self._add_nodes(dot, self)
        dot.render(filename, format=fmt, cleanup=True, view=True)  # 传递格式参数
        return dot

    def _add_nodes(self, dot, node):
        if node is None:
            return
        # 使用节点内存地址生成唯一ID（解决相同值冲突）
        node_id = str(id(node))  # 关键优化点1：确保唯一性
        dot.node(node_id, str(node.val), shape='circle', style='filled', fillcolor='lightblue')

        # 处理左子树
        if node.left:
            left_id = str(id(node.left))
            dot.edge(node_id, left_id, label='L', color='#1E90FF')  # DodgerBlue
            self._add_nodes(dot, node.left)
        else:
            # 透明占位符保持结构对称
            dot.node(f"{node_id}_L", "", shape='point', style='invis')
            dot.edge(node_id, f"{node_id}_L", style='invis')

        # 处理右子树
        if node.right:
            right_id = str(id(node.right))
            dot.edge(node_id, right_id, label='R', color='#DC143C')  # Crimson
            self._add_nodes(dot, node.right)
        else:
            dot.node(f"{node_id}_R", "", shape='point', style='invis')
            dot.edge(node_id, f"{node_id}_R", style='invis')

    def show(self):
        lines, *_ = self._display_aux()
        for line in lines:
            print(line)

    def _display_aux(self):
        """返回子树的显示行、宽度、高度和根节点水平位置"""
        # 无子节点情况
        if self.right is None and self.left is None:
            line = f"{self.val}"
            width = len(line)
            height = 1
            middle = width // 2
            return [line], width, height, middle

        # 只有左子节点情况
        if self.right is None:
            lines, n, p, x = self.left._display_aux()
            s = f"{self.val}"
            u = len(s)
            first_line = (x + 1) * ' ' + (n - x - 1) * '_' + s
            second_line = x * ' ' + '/' + (n - x - 1 + u) * ' '
            shifted_lines = [line + u * ' ' for line in lines]
            return [first_line, second_line] + shifted_lines, n + u, p + 2, n + u // 2

        # 只有右子节点情况
        if self.left is None:
            lines, n, p, x = self.right._display_aux()
            s = f"{self.val}"
            u = len(s)
            first_line = s + x * '_' + (n - x) * ' '
            second_line = (u + x) * ' ' + '\\' + (n - x - 1) * ' '
            shifted_lines = [u * ' ' + line for line in lines]
            return [first_line, second_line] + shifted_lines, n + u, p + 2, u // 2

        # 存在左右子节点情况
        left, n, p, x = self.left._display_aux()
        right, m, q, y = self.right._display_aux()
        s = f"{self.val}"
        u = len(s)
        first_line = (x + 1) * ' ' + (n - x - 1) * '_' + s + y * '_' + (m - y) * ' '
        second_line = x * ' ' + '/' + (n - x - 1 + u + y) * ' ' + '\\' + (m - y - 1) * ' '

        # 合并左右子树
        if p < q:
            left += [' ' * n] * (q - p)
        elif q < p:
            right += [' ' * m] * (p - q)
        zipped_lines = zip(left, right)
        lines = [first_line, second_line] + [a + ' ' * u + b for a, b in zipped_lines]
        return lines, n + m + u, max(p, q) + 2, n + u // 2
