from flask import session

from models import User


def get_active_session_user():
    """返回当前会话关联且仍启用的用户。

    返回 (user, state)，其中 state 可能是:
    - None: 用户有效
    - "missing": 未登录或用户不存在
    - "disabled": 账号已禁用
    """
    username = session.get("username")
    if not username:
        return None, "missing"

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return None, "missing"

    if user.status != 1:
        session.clear()
        return None, "disabled"

    return user, None
