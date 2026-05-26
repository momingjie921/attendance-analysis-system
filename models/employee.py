# models/employee.py
from datetime import datetime, date
from models import db
from sqlalchemy.dialects.mysql import INTEGER

class Employee(db.Model):
    """员工表（与SQL表结构完全匹配）"""
    __tablename__ = 'employee'

    # 字段定义
    emp_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True, comment='员工唯一ID')
    emp_name = db.Column(db.String(30), nullable=False, comment='员工姓名')
    emp_code = db.Column(db.String(20), unique=True, nullable=False, comment='员工编号')
    dept_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('department.dept_id'), nullable=False, comment='所属部门ID')
    phone = db.Column(db.String(20), unique=True, nullable=True, comment='手机号')
    email = db.Column(db.String(50), unique=True, nullable=True, comment='邮箱')
    entry_time = db.Column(db.Date, nullable=True, comment='入职时间')
    status = db.Column(db.SmallInteger, default=1, comment='状态：1-在职 0-离职')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系定义
    attendances = db.relationship(
        'Attendance',
        back_populates='employee',
        lazy='dynamic',
        foreign_keys='[Attendance.emp_id]'
    )
    leaves = db.relationship(
        'Leave',
        back_populates='employee',
        lazy='dynamic',
        foreign_keys='[Leave.emp_id]'
    )
    abnormal_attendances = db.relationship(
        'AbnormalAttendance',
        back_populates='employee',
        lazy='dynamic',
        foreign_keys='[AbnormalAttendance.emp_id]'
    )
    approved_leaves = db.relationship(
        'Leave',
        back_populates='approver_emp',
        lazy='dynamic',
        foreign_keys='[Leave.approver_id]',
        primaryjoin='Employee.emp_id == Leave.approver_id'
    )
    user = db.relationship(
        'User',
        back_populates='employee',
        lazy='joined',
        uselist=False
    )

    def __repr__(self):
        return f"<Employee {self.emp_name}({self.emp_code})>"
