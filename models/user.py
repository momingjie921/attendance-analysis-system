from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from sqlalchemy.dialects.mysql import INTEGER


class User(db.Model):
    """用户表（与SQL表结构完全匹配）"""
    __tablename__ = 'user'

    # 修正字段类型为UNSIGNED
    user_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True, comment='用户唯一ID')
    emp_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('employee.emp_id'), unique=True, nullable=False,
                       comment='关联员工ID')
    username = db.Column(db.String(50), unique=True, nullable=False, comment='登录账号')
    password = db.Column(db.String(255), nullable=False, comment='加密密码（SHA256+盐值）')
    role = db.Column(db.Enum('admin', 'manager', 'employee'), default='employee', comment='角色')
    last_login_time = db.Column(db.DateTime, nullable=True, comment='最后登录时间')
    status = db.Column(db.SmallInteger, default=1, comment='状态：1-启用 0-禁用')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 索引
    __table_args__ = (
        db.Index('idx_username', 'username'),
        db.Index('idx_role', 'role'),
        db.Index('idx_status', 'status'),
        db.Index('idx_emp_id', 'emp_id'),
    )

    # 关系定义
    employee = db.relationship(
        'Employee',
        back_populates='user',
        lazy='joined'
    )

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        # 如果有密码传入，自动加密
        if 'password' in kwargs:
            self.set_password(kwargs['password'])

    def set_password(self, password):
        """设置密码（自动加密）"""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        if not self.password:
            return False
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<User {self.username}({self.role})>"