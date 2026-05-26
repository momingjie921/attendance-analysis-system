# models/department.py
from datetime import datetime
from models import db
from sqlalchemy.dialects.mysql import INTEGER

class Department(db.Model):
    """部门表（与SQL表结构完全匹配）"""
    __tablename__ = 'department'

    # 字段定义
    dept_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True, comment='部门唯一ID')
    dept_name = db.Column(db.String(50), nullable=False, comment='部门名称')
    dept_code = db.Column(db.String(20), unique=True, nullable=False, comment='部门编码')
    manager_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), nullable=True, comment='部门负责人ID')
    phone = db.Column(db.String(20), nullable=True, comment='联系电话')
    email = db.Column(db.String(50), nullable=True, comment='邮箱地址')
    parent_dept_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('department.dept_id'), nullable=True, comment='上级部门ID（NULL为一级部门）')
    status = db.Column(db.SmallInteger, default=1, comment='状态：1-启用 0-禁用')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 自关联关系（上级部门）
    parent = db.relationship(
        'Department',
        remote_side=[dept_id],
        foreign_keys=[parent_dept_id],
        backref='children',
        lazy='joined',
        primaryjoin='Department.parent_dept_id == Department.dept_id'
    )

    # 部门负责人关联
    manager = db.relationship(
        'Employee',
        backref='managed_departments',
        lazy='joined',
        foreign_keys=[manager_id],
        primaryjoin='Department.manager_id == Employee.emp_id'
    )

    # 部门下的员工
    employees = db.relationship(
        'Employee',
        backref='department',
        lazy='dynamic',
        foreign_keys='[Employee.dept_id]',
        primaryjoin='Department.dept_id == Employee.dept_id'
    )

    # 索引
    __table_args__ = (
        db.Index('idx_manager_id', 'manager_id'),
        db.Index('idx_parent_dept_id', 'parent_dept_id'),
    )

    def __repr__(self):
        return f"<Department {self.dept_name}>"