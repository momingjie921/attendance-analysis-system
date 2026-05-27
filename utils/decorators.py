# utils/decorators.py
from flask import jsonify
from functools import wraps

from utils.session_auth import get_active_session_user

def api_role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user, state = get_active_session_user()
            if not user:
                if state == "disabled":
                    return jsonify({"code": 401, "msg": "账号已禁用，请联系管理员"}), 401
                return jsonify({"code": 401, "msg": "未登录，请先登录"}), 401

            current_role = user.role
            if current_role not in allowed_roles:
                return jsonify({"code": 403, "msg": "权限不足"}), 403
            return view_func(*args, **kwargs)
        return wrapper
    return decorator
