# api/__init__.py
from flask import Blueprint

# 创建API蓝图（统一前缀为/api）
api_bp = Blueprint('api', __name__, url_prefix='/api')