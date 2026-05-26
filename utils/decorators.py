# utils/decorators.py
from flask import jsonify, session
from functools import wraps

def api_role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return jsonify({"code": 401, "msg": "未登录"}), 401
            current_role = session.get("role")
            if current_role not in allowed_roles:
                return jsonify({"code": 403, "msg": "权限不足"}), 403
            return view_func(*args, **kwargs)
        return wrapper
    return decorator