# models/leave.py
from datetime import datetime
from models import db
from sqlalchemy.dialects.mysql import INTEGER

class Leave(db.Model):
    """请假记录表（与SQL表结构完全匹配）"""
    __tablename__ = 'leave_record'

    # 字段定义
    leave_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True, comment='请假记录ID')
    emp_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=False, comment='关联员工ID')
    leave_type = db.Column(db.Enum('annual','sick','personal','maternity','other'), nullable=False, comment='请假类型')
    start_date = db.Column(db.Date, nullable=False, comment='请假开始日期')
    end_date = db.Column(db.Date, nullable=False, comment='请假结束日期')
    leave_days = db.Column(db.Numeric(3,1), nullable=False, comment='请假天数（如0.5天）')
    leave_half_day = db.Column(db.Enum('AM','PM'), nullable=True, comment='半天请假：AM-上午 PM-下午')
    approval_status = db.Column(db.Enum('pending','approved','rejected'), default='pending', comment='审批状态')
    approver_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=True, comment='审批人ID（关联employee）')
    approval_remark = db.Column(db.String(500), nullable=True, comment='审批备注')
    remark = db.Column(db.String(500), nullable=True, comment='请假备注')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 索引
    __table_args__ = (
        db.Index('idx_emp_id', 'emp_id'),
        db.Index('idx_start_end_date', 'start_date', 'end_date'),
    )

    # 关系定义
    employee = db.relationship(
        'Employee',
        back_populates='leaves',
        foreign_keys=[emp_id],
        lazy='joined'
    )
    approver_emp = db.relationship(
        'Employee',
        back_populates='approved_leaves',
        foreign_keys=[approver_id],
        lazy='joined'
    )

    def __repr__(self):
        return f"<Leave {self.emp_id} {self.leave_type} {self.approval_status}>"
