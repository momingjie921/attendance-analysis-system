# app.py

from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify, g
from functools import wraps
import os
import logging
import secrets
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_caching import Cache
from flask_cors import CORS
from flask_apscheduler import APScheduler

load_dotenv()

from config.database import init_database, db
from models import User, Employee, Department

from api import api_bp
from utils.error_handlers import register_error_handlers

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
is_debug = os.getenv("FLASK_DEBUG", "False") == "True"

# 从环境变量读取配置
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    secret_key = os.urandom(32).hex()
    logging.warning('SECRET_KEY not set. Generated a temporary key for this process.')
app.secret_key = secret_key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)  # 会话超时2小时
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', str(not is_debug)).lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['API_CSRF_PROTECT'] = os.getenv('API_CSRF_PROTECT', 'true').lower() == 'true'

# CSRF配置：只对网页表单启用，对API禁用
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # 禁用默认CSRF检查
app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'DELETE', 'PATCH']  # 检查的方法

# 初始化CORS
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
allowed_origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
CORS(app, supports_credentials=True, origins=allowed_origins)

# 初始化CSRF保护
csrf = CSRFProtect(app)

# 对API蓝图禁用CSRF保护（避免API请求因缺少Token被拦截）
csrf.exempt(api_bp)

# 初始化定时任务调度器
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# 配置缓存
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300
})

# 配置日志记录
logging.basicConfig(
    filename='logs/app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加请求日志中间件
@app.before_request
def log_request_info():
    """记录每个请求的信息"""
    if request.path.startswith('/static/'):
        return  # 跳过静态文件请求

    g.start_time = datetime.now()
    logging.info(f'[{request.remote_addr}] {request.method} {request.path} - User: {session.get("username", "Anonymous")}')

    if request.path.startswith('/api/') and request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
        if "username" not in session:
            return jsonify({"code": 401, "msg": "未登录，请先登录"}), 401
        if app.config['API_CSRF_PROTECT']:
            expected_token = session.get('api_csrf_token')
            actual_token = request.headers.get('X-CSRF-Token')
            if not expected_token or expected_token != actual_token:
                return jsonify({"code": 403, "msg": "CSRF token 无效"}), 403

@app.after_request
def log_response_info(response):
    """记录响应信息"""
    if hasattr(g, 'start_time'):
        duration = (datetime.now() - g.start_time).total_seconds() * 1000  # 毫秒
        logging.info(f'Response: {response.status_code} - Duration: {duration:.2f}ms')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

init_database(app)

from api.employee_management_api import (
    get_employee_list, create_employee, update_employee,
    delete_employee, get_department_list, reset_user_password, create_user_account, permanent_delete_employee,
    get_employee_detail
)
from api.department_management_api import (
    get_department_list_full, create_department, update_department,
    toggle_department_status, permanent_delete_department, get_department_tree
)
from api.dashboard_api import get_dashboard_data
from api.department_api import get_dept_data
from api.employee_api import (
    get_employee_data, get_attendance_list, get_abnormal_list_paginated, update_abnormal_remark
)
from api.export_api import export_data
from api.manager_api import manager_bp

# 手动注册路由到蓝图
api_bp.add_url_rule('/dashboard/data', view_func=get_dashboard_data, methods=['GET'])
api_bp.add_url_rule('/dept/data', view_func=get_dept_data, methods=['GET'])
api_bp.add_url_rule('/employee/data', view_func=get_employee_data, methods=['GET'])
api_bp.add_url_rule('/employee/attendance/list', view_func=get_attendance_list, methods=['GET'])
api_bp.add_url_rule('/employee/abnormal/list', view_func=get_abnormal_list_paginated, methods=['GET'])
api_bp.add_url_rule('/employee/abnormal/update-remark', view_func=update_abnormal_remark, methods=['POST'])
api_bp.add_url_rule('/export', view_func=export_data, methods=['GET'])

# 员工管理API
api_bp.add_url_rule('/employees/list', view_func=get_employee_list, methods=['GET'])
api_bp.add_url_rule('/employees/detail', view_func=get_employee_detail, methods=['GET'])
api_bp.add_url_rule('/employees/create', view_func=create_employee, methods=['POST'])
api_bp.add_url_rule('/employees/update', view_func=update_employee, methods=['PUT'])
api_bp.add_url_rule('/employees/delete', view_func=delete_employee, methods=['DELETE'])
api_bp.add_url_rule('/employees/departments', view_func=get_department_list, methods=['GET'])
api_bp.add_url_rule('/employees/create-account', view_func=create_user_account, methods=['POST'])
api_bp.add_url_rule('/employees/reset-password', view_func=reset_user_password, methods=['POST'])
api_bp.add_url_rule('/employees/permanent-delete', view_func=permanent_delete_employee, methods=['DELETE'])

# 部门管理API
api_bp.add_url_rule('/departments/list', view_func=get_department_list_full, methods=['GET'])
api_bp.add_url_rule('/departments/tree', view_func=get_department_tree, methods=['GET'])
api_bp.add_url_rule('/departments/create', view_func=create_department, methods=['POST'])
api_bp.add_url_rule('/departments/update', view_func=update_department, methods=['PUT'])
api_bp.add_url_rule('/departments/toggle-status', view_func=toggle_department_status, methods=['PUT'])
api_bp.add_url_rule('/departments/permanent-delete', view_func=permanent_delete_department, methods=['DELETE'])

from api.import_api import import_bp
from api.config_api import config_bp
from api.backup_api import backup_bp, perform_auto_backup
from api.warning_api import warning_bp
from api.leave_api import leave_bp
from api.holiday_api import holiday_bp

app.register_blueprint(import_bp, url_prefix='/api')
app.register_blueprint(config_bp, url_prefix='/api')
app.register_blueprint(backup_bp, url_prefix='/api')
app.register_blueprint(manager_bp, url_prefix='/api')
app.register_blueprint(warning_bp, url_prefix='/api')
app.register_blueprint(leave_bp, url_prefix='/api')
app.register_blueprint(holiday_bp, url_prefix='/api')

# 注册定时任务：每天凌晨2点执行自动备份
@scheduler.task('cron', id='daily_backup', hour=2, minute=0)
def auto_backup_job():
    with app.app_context():
        perform_auto_backup()

app.register_blueprint(api_bp)

# 注册全局错误处理器
register_error_handlers(app)


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))

            # 检查会话是否过期
            last_activity = session.get('last_activity')
            if last_activity:
                last_activity_time = datetime.fromisoformat(last_activity)
                if datetime.now() - last_activity_time > timedelta(hours=2):
                    session.clear()
                    return redirect(url_for("login"))

            # 更新最后活动时间
            session['last_activity'] = datetime.now().isoformat()
            session.permanent = True

            current_role = session.get("role")
            if current_role not in allowed_roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def init_base_data():
    with app.app_context():
        # 先创建所有表
        db.create_all()
        # 初始化默认部门
        if not Department.query.filter_by(dept_code='001').first():
            dept = Department(dept_name='总经办', dept_code='001', parent_dept_id=None)
            db.session.add(dept)
            db.session.commit()

        # 初始化管理员员工
        dept = Department.query.filter_by(dept_code='001').first()
        if not Employee.query.filter_by(emp_code='admin001').first():
            emp = Employee(emp_code='admin001', emp_name='系统管理员', dept_id=dept.dept_id, entry_time=date.today())
            db.session.add(emp)
            db.session.commit()

        # 初始化管理员用户
        emp = Employee.query.filter_by(emp_code='admin001').first()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', emp_id=emp.emp_id, role='admin', password='admin123')
            db.session.add(admin)

        # 初始化经理用户
        if not Department.query.filter_by(dept_code='002').first():
            tech_dept = Department(dept_name='技术部', dept_code='002', parent_dept_id=None)
            db.session.add(tech_dept)
            db.session.commit()

        tech_dept = Department.query.filter_by(dept_code='002').first()
        if not Employee.query.filter_by(emp_code='tech001').first():
            manager_emp = Employee(emp_code='tech001', emp_name='李经理', dept_id=tech_dept.dept_id,
                                   entry_time=date.today())
            db.session.add(manager_emp)
            db.session.commit()

        manager_emp = Employee.query.filter_by(emp_code='tech001').first()
        if not User.query.filter_by(username='tech_manager').first():
            manager = User(username='tech_manager', emp_id=manager_emp.emp_id, role='manager', password='manager123')
            db.session.add(manager)

        # 初始化普通员工
        if not Employee.query.filter_by(emp_code='tech002').first():
            emp_emp = Employee(emp_code='tech002', emp_name='张三', dept_id=tech_dept.dept_id, entry_time=date.today())
            db.session.add(emp_emp)
            db.session.commit()

        emp_emp = Employee.query.filter_by(emp_code='tech002').first()
        if not User.query.filter_by(username='zhangsan').first():
            employee = User(username='zhangsan', emp_id=emp_emp.emp_id, role='employee', password='employee123')
            db.session.add(employee)

        db.session.commit()


enable_demo_data = os.getenv('ENABLE_DEMO_DATA', 'false').lower() == 'true'
if enable_demo_data:
    init_base_data()
else:
    with app.app_context():
        db.create_all()


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        # 从数据库查询用户
        user = User.query.filter_by(username=username).first()
        # 验证用户和密码（修正：使用verify_password）
        if not user or not user.check_password(password):
            return render_template("login.html", error="账号或密码错误！")

        # 检查账号状态
        if user.status == 0:
            return render_template("login.html", error="账号已禁用，请联系管理员！")

        # 更新最后登录时间
        user.last_login_time = datetime.now()
        db.session.commit()

        # 从员工表获取部门、姓名等信息
        emp = user.employee
        dept = emp.department.dept_name if emp.department else '未知部门'
        emp_name = emp.emp_name

        # 存入session
        session["username"] = user.username
        session["role"] = user.role
        session["dept"] = dept
        session["name"] = emp_name
        session["emp_id"] = emp.emp_id
        session["last_activity"] = datetime.now().isoformat()
        session["api_csrf_token"] = secrets.token_hex(32)
        session.permanent = True

        # 角色跳转
        role_to_dashboard = {
            "admin": "admin_dashboard",
            "manager": "manager_dashboard",
            "employee": "employee_dashboard"
        }
        return redirect(url_for(role_to_dashboard[user.role]))
    return render_template("login.html")


@app.route("/admin/dashboard")
@role_required(["admin"])
def admin_dashboard():
    # 获取当前月份
    current_month = datetime.now().strftime('%Y-%m')

    # 直接从数据库获取部门列表（用于部门下拉框）
    depts = Department.query.filter_by(status=1).all()
    departments = [{'dept_code': dept.dept_code, 'dept_name': dept.dept_name} for dept in depts]

    # 仅传递必要的用户信息和部门列表
    template_vars = {
        "username": session["username"],
        "role": session["role"],
        "name": session["name"],
        "current_month": current_month,
        "departments": departments  # 只保留部门列表用于下拉框
    }
    return render_template("admin-dashboard.html", **template_vars)


@app.route("/admin/data-import")
@role_required(["admin"])
def admin_data_import():
    return render_template(
        "pages/admin/data-import.html",
        username=session["username"],
        role=session["role"],
        name=session["name"]
    )


@app.route("/admin/data-backup")
@role_required(["admin"])
def admin_data_backup():
    return render_template(
        "pages/admin/data-backup.html",
        username=session["username"],
        dept=session["dept"],
        name=session["name"]
    )


@app.route("/admin/department-management")
@role_required(["admin"])
def admin_department_management():
    return render_template(
        "pages/admin/department-management.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/admin/employee-management")
@role_required(["admin"])
def admin_employee_management():
    return render_template(
        "pages/admin/employee-management.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/admin/rule-config")
@role_required(["admin"])
def admin_rule_config():
    return render_template(
        "pages/admin/rule-config.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/admin/holiday-calendar")
@role_required(["admin"])
def admin_holiday_calendar():
    return render_template(
        "pages/admin/holiday-calendar.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/admin/leave-approval")
@role_required(["admin"])
def admin_leave_approval():
    return render_template(
        "pages/admin/leave-approval.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/manager/leave-approval")
@role_required(["manager"])
def manager_leave_approval():
    return render_template(
        "pages/admin/leave-approval.html", # 复用同一个模板
        username=session["username"],
        name=session["name"]
    )


@app.route("/admin/attendance-warning")
@role_required(["admin"])
def admin_attendance_warning():
    return render_template(
        "pages/admin/attendance-warning.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/manager/dashboard")
@role_required(["manager"])
def manager_dashboard():
    return render_template(
        "manager-dashboard.html",
        username=session["username"],
        role=session["role"],
        name=session["name"],
        dept=session["dept"]
    )


@app.route("/manager/data-import")
@role_required(["manager"])
def manager_data_import():
    return render_template(
        "pages/manager/data-import.html",
        username=session["username"],
        role=session["role"],
        name=session["name"],
        dept=session["dept"]
    )


@app.route("/manager/departmental-abnormal")
@role_required(["manager"])
def manager_departmental_abnormal():
    return render_template(
        "pages/manager/departmental-abnormal.html",
        username=session["username"],
        dept=session["dept"],
        name=session["name"]
    )


@app.route("/manager/departmental-analysis")
@role_required(["manager"])
def manager_departmental_analysis():
    return render_template(
        "pages/manager/departmental-analysis.html",
        username=session["username"],
        dept=session["dept"],
        name=session["name"]
    )


@app.route("/employee/dashboard")
@role_required(["employee", "manager", "admin"])
def employee_dashboard():
    return render_template(
        "employee-dashboard.html",
        username=session["username"],
        role=session["role"],
        name=session["name"],
        dept=session["dept"]
    )


@app.route("/employee/abnormal-record")
@role_required(["employee", "manager", "admin"])
def employee_abnormal_record():
    return render_template(
        "pages/employee/abnormal-record.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/employee/leave-apply")
@role_required(["employee", "manager", "admin"])
def employee_leave_apply():
    return render_template(
        "pages/employee/leave-apply.html",
        username=session["username"],
        name=session["name"]
    )


@app.route("/employee/attendance-record")
@role_required(["employee", "manager", "admin"])
def employee_attendance_record():
    return render_template(
        "pages/employee/attendance-record.html",
        username=session["username"],
        name=session["name"],
        dept=session["dept"]
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/csrf-token", methods=["GET"])
def get_api_csrf_token():
    if "username" not in session:
        return jsonify({"code": 401, "msg": "未登录，请先登录"}), 401
    token = session.get("api_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["api_csrf_token"] = token
    return jsonify({"code": 200, "msg": "ok", "data": {"csrf_token": token}})


@app.errorhandler(403)
def forbidden(e):
    # 判断是否为API请求
    if request.path.startswith('/api/'):
        return jsonify({"code": 403, "msg": "权限不足，无法访问该接口"}), 403
    # 网页请求返回原有页面
    return f"""
    <div style="text-align:center; margin-top:50px;">
        <h1>403 权限不足</h1>
        <p>你没有访问该页面的权限！</p>
        <a href="{url_for('login')}">返回登录页</a>
    </div>
    """, 403


@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"code": 401, "msg": "未登录，请先登录"}), 401


if __name__ == "__main__":
    # 从环境变量读取运行配置
    app.run(
        debug=is_debug,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 5000))
    )
