# utils/cache_utils.py
from flask import current_app, request
from functools import wraps
import hashlib
import json


def cached(timeout=300, key_prefix=''):
    """
    缓存装饰器，用于API函数

    Args:
        timeout: 缓存超时时间（秒）
        key_prefix: 缓存键前缀
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 如果缓存不可用，直接执行函数
            if not hasattr(current_app, 'cache'):
                return func(*args, **kwargs)

            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}"
            
            # 从 request.args 获取 URL 参数用于缓存 key
            try:
                if request and request.args:
                    args_dict = dict(sorted(request.args.items()))
                    args_str = json.dumps(args_dict, sort_keys=True)
                    cache_key += f":{hashlib.md5(args_str.encode()).hexdigest()}"
            except Exception:
                pass
            
            # 尝试从缓存获取
            cached_result = current_app.cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            current_app.cache.set(cache_key, result, timeout=timeout)
            return result

        return wrapper
    return decorator


def clear_cache(key_prefix=''):
    if hasattr(current_app, 'cache'):
        current_app.cache.clear()

