# utils/error_handlers.py
import logging
from typing import Dict, Any, Optional
from flask import jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DataError
from werkzeug.exceptions import HTTPException


def handle_sqlalchemy_error(error: SQLAlchemyError) -> tuple[Dict[str, Any], int]:
    """处理SQLAlchemy数据库错误"""
    logging.error(f"Database error: {str(error)}")
    # 安全地回滚数据库会话
    try:
        if hasattr(current_app, 'db') and hasattr(current_app.db, 'session'):
            current_app.db.session.rollback()
    except Exception:
        pass  # 忽略回滚错误

    if isinstance(error, IntegrityError):
        return {
            "code": 400,
            "msg": "数据完整性错误，请检查输入数据",
            "error": str(error)
        }, 400
    elif isinstance(error, DataError):
        return {
            "code": 400,
            "msg": "数据格式错误",
            "error": str(error)
        }, 400
    else:
        return {
            "code": 500,
            "msg": "数据库操作失败",
            "error": str(error)
        }, 500


def handle_http_error(error: HTTPException) -> tuple[Dict[str, Any], int]:
    """处理HTTP异常"""
    logging.warning(f"HTTP error {error.code}: {error.description}")
    return {
        "code": error.code,
        "msg": error.description,
        "error": str(error)
    }, error.code


def handle_generic_error(error: Exception) -> tuple[Dict[str, Any], int]:
    """处理通用异常"""
    logging.error(f"Unexpected error: {str(error)}", exc_info=True)
    return {
        "code": 500,
        "msg": "服务器内部错误",
        "error": str(error)
    }, 500


def register_error_handlers(app):
    """注册全局错误处理器"""

    @app.errorhandler(SQLAlchemyError)
    def sqlalchemy_error_handler(error):
        return handle_sqlalchemy_error(error)

    @app.errorhandler(HTTPException)
    def http_error_handler(error):
        return handle_http_error(error)

    @app.errorhandler(Exception)
    def generic_error_handler(error):
        return handle_generic_error(error)


def api_error_response(code: int, message: str, error_details: Optional[str] = None) -> Dict[str, Any]:
    """统一的API错误响应格式"""
    response = {
        "code": code,
        "msg": message
    }
    if error_details and current_app.debug:
        response["error"] = error_details
    return response