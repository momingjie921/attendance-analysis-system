# utils/pagination.py
from typing import List, Any, Callable, Optional, Dict, Union
from flask import request, jsonify
from math import ceil


class Pagination:
    """分页工具类"""

    def __init__(self, query: Any, page: Optional[int] = None, per_page: Optional[int] = None, max_per_page: int = 100):
        """
        初始化分页对象

        Args:
            query: SQLAlchemy查询对象
            page: 当前页码（从1开始）
            per_page: 每页条数
            max_per_page: 最大每页条数限制
        """
        self.page = page or int(request.args.get('page', 1))
        self.per_page = min(per_page or int(request.args.get('per_page', 20)), max_per_page)
        self.total = query.count()
        self.pages = ceil(self.total / self.per_page) if self.per_page > 0 else 1
        self.has_prev = self.page > 1
        self.has_next = self.page < self.pages

        # 计算偏移量
        offset = (self.page - 1) * self.per_page
        self.items = query.offset(offset).limit(self.per_page).all()

    def to_dict(self):
        """转换为字典格式"""
        return {
            'items': self.items,
            'page': self.page,
            'per_page': self.per_page,
            'total': self.total,
            'pages': self.pages,
            'has_prev': self.has_prev,
            'has_next': self.has_next
        }


def paginate_query(query: Any, page: Optional[int] = None, per_page: Optional[int] = None, max_per_page: int = 100) -> Pagination:
    """
    分页查询便捷函数

    Args:
        query: SQLAlchemy查询对象
        page: 当前页码
        per_page: 每页条数
        max_per_page: 最大每页条数

    Returns:
        Pagination对象
    """
    return Pagination(query, page, per_page, max_per_page)


def api_paginated_response(pagination: Pagination, serializer: Optional[Callable[[Any], Dict[str, Any]]] = None, **kwargs: Any) -> Any:
    """
    生成分页API响应

    Args:
        pagination: Pagination对象
        serializer: 数据序列化函数
        **kwargs: 额外响应数据

    Returns:
        JSON响应
    """
    data = pagination.to_dict()

    # 如果有序列化函数，序列化items
    if serializer and callable(serializer):
        data['items'] = [serializer(item) for item in data['items']]

    # 添加额外数据
    data.update(kwargs)

    return jsonify({
        'code': 200,
        'msg': '查询成功',
        'data': data
    })