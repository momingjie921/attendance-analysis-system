# models/attendance.py
from datetime import datetime
from models import db
from sqlalchemy.dialects.mysql import INTEGER, BIGINT

class Attendance(db.Model):
    """考勤记录表（与SQL表结构完全匹配）"""
    __tablename__ = 'attendance_record'

    # 字段定义
    att_id = db.Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment='考勤记录ID')
    emp_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=False, comment='关联员工ID')
    att_date = db.Column(db.Date, nullable=False, comment='考勤日期')
    check_in_time = db.Column(db.DateTime, nullable=True, comment='上班打卡时间（NULL为未打卡）')
    check_out_time = db.Column(db.DateTime, nullable=True, comment='下班打卡时间（NULL为未打卡）')
    late_minutes = db.Column(db.Integer, default=0, comment='迟到分钟数（0为未迟到）')
    early_minutes = db.Column(db.Integer, default=0, comment='早退分钟数（0为未早退）')
    work_duration = db.Column(db.Integer, nullable=True, comment='当日工作时长（分钟，NULL为未统计）')
    is_absent = db.Column(db.SmallInteger, default=0, comment='是否旷工：1-是 0-否（结合请假表判定）')
    import_batch = db.Column(db.String(50), nullable=True, comment='数据导入批次号（关联import_log表）')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 索引
    __table_args__ = (
        db.UniqueConstraint('emp_id', 'att_date', name='uk_emp_date'),
        db.Index('idx_att_date', 'att_date'),
        db.Index('idx_emp_id', 'emp_id'),
    )

    # 关系定义
    employee = db.relationship(
        'Employee',
        back_populates='attendances',
        lazy='joined'
    )

    def __repr__(self):
        return f"<Attendance {self.emp_id} {self.att_date}>"