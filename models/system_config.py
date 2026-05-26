# models/system_config.py
from datetime import datetime
from models import db

class SystemConfig(db.Model):
    """系统配置表（与SQL表结构完全匹配）"""
    __tablename__ = 'system_config'

    # 字段定义：完全匹配SQL
    config_id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='配置ID')  # 修正：config_id
    config_key = db.Column(db.String(50), unique=True, nullable=False, comment='配置键')
    config_value = db.Column(db.String(100), nullable=False, comment='配置值')
    config_desc = db.Column(db.String(200), nullable=True, comment='配置说明')
    config_type = db.Column(db.Enum('time','number','string'), nullable=False, comment='配置类型')  # 补充：匹配SQL的config_type
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 索引：匹配SQL
    __table_args__ = (
        db.Index('idx_config_key', 'config_key'),
    )

    def __repr__(self):
        return f"<SystemConfig {self.config_key}={self.config_value}>"