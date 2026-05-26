# models/import_log.py
from datetime import datetime
from models import db
from sqlalchemy.dialects.mysql import INTEGER, BIGINT

class ImportLog(db.Model):
    """数据导入日志表（与SQL表结构完全匹配）"""
    __tablename__ = 'import_log'

    # 字段定义
    log_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True, comment='日志ID')
    import_batch = db.Column(db.String(50), unique=True, nullable=False, comment='导入批次号')
    import_user_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('user.user_id'), nullable=False, comment='导入人ID（关联user）')
    file_name = db.Column(db.String(200), nullable=False, comment='导入文件名')
    file_size = db.Column(BIGINT(unsigned=True), nullable=True, comment='文件大小（字节）')
    total_rows = db.Column(INTEGER(unsigned=True), default=0, comment='文件总行数')
    success_rows = db.Column(INTEGER(unsigned=True), default=0, comment='导入成功行数')
    fail_rows = db.Column(INTEGER(unsigned=True), default=0, comment='导入失败行数')
    fail_reason = db.Column(db.Text, nullable=True, comment='失败原因（JSON格式存储）')
    import_status = db.Column(db.Enum('success','failed','processing', 'success_with_errors'), nullable=False, comment='导入状态')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='导入时间')

    # 关联关系
    importer = db.relationship('User', backref='import_logs', lazy='joined')

    # 索引
    __table_args__ = (
        db.Index('idx_import_batch', 'import_batch'),
        db.Index('idx_import_user_id', 'import_user_id'),
    )

    def __repr__(self):
        return f"<ImportLog {self.import_batch} {self.import_status}>"