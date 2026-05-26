# models/abnormal_attendance.py
from datetime import datetime
from models import db
from enum import Enum
from sqlalchemy.dialects.mysql import INTEGER, BIGINT

# 定义异常类型枚举（值与数据库中的枚举值一致，使用大写以便匹配）
class AbnormalTypeEnum(Enum):
    LATE = 'LATE'
    EARLY = 'EARLY'
    ABSENT = 'ABSENT'
    MISSING_CHECK = 'MISSING_CHECK'

class AbnormalAttendance(db.Model):
    """异常考勤汇总表（与SQL表结构完全匹配）"""
    __tablename__ = 'abnormal_attendance'

    # 字段定义
    abnormal_id = db.Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment='异常记录ID')
    emp_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=False, comment='员工ID')
    abnormal_date = db.Column(db.Date, nullable=False, comment='异常日期')
    abnormal_type = db.Column(db.Enum(AbnormalTypeEnum), nullable=False, comment='异常类型：late/early/absent/missing_check')
    abnormal_desc = db.Column(db.String(200), nullable=True, comment='异常描述')
    is_processed = db.Column(db.SmallInteger, default=0, comment='是否已处理：1-是 0-否')
    processor_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=True, comment='处理人ID')
    process_remark = db.Column(db.String(500), nullable=True, comment='处理备注')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系定义
    employee = db.relationship(
        'Employee',
        back_populates='abnormal_attendances',
        foreign_keys=[emp_id],
        lazy='joined'
    )
    processor = db.relationship(
        'Employee',
        backref='processed_abnormals',
        lazy='joined',
        foreign_keys=[processor_id]
    )

    # 唯一索引
    __table_args__ = (
        db.UniqueConstraint('emp_id', 'abnormal_date', 'abnormal_type', name='uq_emp_date_type'),
        db.Index('idx_emp_id', 'emp_id'),
        db.Index('idx_abnormal_date', 'abnormal_date'),
        db.Index('idx_is_processed', 'is_processed'),
    )

    def __repr__(self):
        return f"<AbnormalAttendance {self.emp_id} {self.abnormal_date} {self.abnormal_type.value}>"