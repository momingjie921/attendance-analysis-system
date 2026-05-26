from flask import Blueprint, request, jsonify, session
from models import db, Employee, Leave, SystemConfig, Department, User
from datetime import datetime, date, timedelta
from utils.decorators import api_role_required
from utils.api_helpers import api_response, get_month_range
from sqlalchemy import func

_leave_schema_checked = False


def _ensure_leave_schema():
    global _leave_schema_checked
    if _leave_schema_checked:
        return
    _leave_schema_checked = True
    try:
        inspector = db.inspect(db.engine)
        cols = [c.get('name') for c in inspector.get_columns('leave_record')]
        ddl = []
        if 'leave_half_day' not in cols:
            ddl.append("ALTER TABLE leave_record ADD COLUMN leave_half_day ENUM('AM','PM') NULL")
        if 'approval_remark' not in cols:
            ddl.append("ALTER TABLE leave_record ADD COLUMN approval_remark VARCHAR(500) NULL")
        if ddl:
            for stmt in ddl:
                db.session.execute(db.text(stmt))
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

leave_bp = Blueprint('leave_api', __name__)

def get_sys_config():
    configs = SystemConfig.query.all()
    return {c.config_key: c.config_value for c in configs}

@leave_bp.route('/leave/pending', methods=['GET'])
@api_role_required(['admin', 'manager'])
def get_pending_leaves():
    """获取待审批的请假申请"""
    try:
        _ensure_leave_schema()
        role = session.get('role')
        emp_id = session.get('emp_id')
        
        query = db.session.query(Leave, Employee.emp_name, Department.dept_name)\
            .join(Employee, Leave.emp_id == Employee.emp_id)\
            .join(Department, Employee.dept_id == Department.dept_id)\
            .join(User, User.emp_id == Employee.emp_id)\
            .filter(Leave.approval_status == 'pending')
            
        # 如果是部门主管，只能看到自己部门的
        if role == 'manager':
            # 获取当前主管所属部门
            curr_emp = Employee.query.get(emp_id)
            if curr_emp:
                query = query.filter(Employee.dept_id == curr_emp.dept_id)
            query = query.filter(Employee.emp_id != emp_id)
            query = query.filter(User.role == 'employee')
        
        pending_list = query.all()
        
        data = []
        for leave, emp_name, dept_name in pending_list:
            data.append({
                "leave_id": leave.leave_id,
                "emp_name": emp_name,
                "dept_name": dept_name,
                "leave_type": leave.leave_type,
                "start_date": leave.start_date.strftime('%Y-%m-%d'),
                "end_date": leave.end_date.strftime('%Y-%m-%d'),
                "leave_days": leave.leave_days,
                "half_day": getattr(leave, 'leave_half_day', None),
                "remark": leave.remark,
                "approval_remark": getattr(leave, 'approval_remark', None),
                "create_time": leave.create_time.strftime('%Y-%m-%d %H:%M')
            })
            
        return api_response(200, "获取成功", data)
    except Exception as e:
        return api_response(500, str(e))

@leave_bp.route('/leave/approve', methods=['POST'])
@api_role_required(['admin', 'manager'])
def approve_leave():
    """批准或驳回请假申请"""
    try:
        _ensure_leave_schema()
        data = request.json
        leave_id = data.get('leave_id')
        action = data.get('action') # 'approved' or 'rejected'
        approval_remark = (data.get('remark') or '').strip()
        
        if not leave_id or not action:
            return api_response(400, "参数缺失")
        
        if action == 'rejected' and not approval_remark:
            return api_response(400, "驳回时必须填写审批备注")
            
        leave = Leave.query.get(leave_id)
        if not leave:
            return api_response(404, "申请记录不存在")

        role = session.get('role')
        if role == 'manager':
            approver_emp_id = session.get('emp_id')
            if approver_emp_id and int(leave.emp_id) == int(approver_emp_id):
                return api_response(403, "无权审批自己的请假")

            curr_emp = Employee.query.get(approver_emp_id)
            applicant_emp = Employee.query.get(leave.emp_id)
            if not curr_emp or not applicant_emp or applicant_emp.dept_id != curr_emp.dept_id:
                return api_response(403, "无权审批其他部门请假")

            applicant_user = User.query.filter_by(emp_id=leave.emp_id).first()
            if applicant_user and applicant_user.role != 'employee':
                return api_response(403, "经理请假需由管理员审批")
            
        leave.approval_status = action
        leave.approver_id = session.get('emp_id')
        if hasattr(leave, 'approval_remark'):
            leave.approval_remark = approval_remark
        
        db.session.commit()
        return api_response(200, f"已{'批准' if action == 'approved' else '驳回'}该申请")
    except Exception as e:
        db.session.rollback()
        return api_response(500, str(e))

@leave_bp.route('/leave/apply', methods=['POST'])
@api_role_required(['employee', 'manager', 'admin'])
def apply_leave():
    """申请请假，并执行规则校验"""
    try:
        _ensure_leave_schema()
        emp_id = session.get('emp_id')
        if not emp_id:
            return api_response(401, "未登录或会话过期")

        data = request.json
        leave_type = data.get('leave_type') # annual, sick, personal, etc.
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        leave_days = float(data.get('leave_days', 0))
        remark = data.get('remark', '')
        half_day = (data.get('half_day') or '').strip().upper()

        if not all([leave_type, start_date_str, end_date_str, leave_days]):
            return api_response(400, "参数不完整")

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # 0. 校验日期合理性及天数匹配
        if start_date > end_date:
            return api_response(400, "开始日期不能晚于结束日期")
        
        date_span = (end_date - start_date).days + 1
        if leave_days > date_span:
            return api_response(400, f"请假天数({leave_days})不能超过日期跨度({date_span}天)")
        
        if leave_days <= 0 or (leave_days * 2) % 1 != 0:
            return api_response(400, "请假天数必须为0.5的倍数")

        if leave_days < 1 and date_span != 1:
            return api_response(400, "半天请假仅支持单日申请，请调整日期范围")

        if leave_days == 0.5 and half_day not in ('AM', 'PM'):
            return api_response(400, "半天请假需选择上午或下午")

        # 如果请假天数小于日期跨度，且差值超过1天（允许0.5天的偏差，比如跨2天请1.5天），则认为逻辑错误
        # 比如请假 0.5 天，但日期跨度 3 天，这是不允许的
        if date_span > 1 and leave_days <= (date_span - 1):
             return api_response(400, f"请假天数({leave_days})与日期范围({start_date_str}至{end_date_str})不匹配，请缩短日期范围或增加天数")

        sys_config = get_sys_config()

        # 1. 校验提前通知时长 (leaveApplyNotice)
        notice_hours = int(sys_config.get('leaveApplyNotice', 24))
        work_start_str = sys_config.get('workStartTime', '09:00')
        if len(work_start_str) == 5: work_start_str += ':00'
        work_start_time = datetime.strptime(work_start_str, '%H:%M:%S').time()
        
        apply_time = datetime.now()
        # 将请假开始日期与上班时间结合，作为真实的请假开始时间点
        start_datetime = datetime.combine(start_date, work_start_time)
        
        if (start_datetime - apply_time) < timedelta(hours=notice_hours):
            return api_response(400, f"请假需提前 {notice_hours} 小时申请")

        # 2. 校验带薪年假额度 (annualLeaveDays) - 按年统计
        if leave_type == 'annual':
            annual_limit = float(sys_config.get('annualLeaveDays', 5))
            # 统计今年已批准的年假
            used_annual = db.session.query(func.sum(Leave.leave_days)).filter(
                Leave.emp_id == emp_id,
                Leave.leave_type == 'annual',
                Leave.approval_status == 'approved',
                Leave.start_date >= date(start_date.year, 1, 1),
                Leave.end_date <= date(start_date.year, 12, 31)
            ).scalar() or 0
            
            if (float(used_annual) + leave_days) > annual_limit:
                return api_response(400, f"年假额度不足。剩余: {annual_limit - float(used_annual)} 天")

        # 3. 校验带薪病假额度 (sickLeaveDays) - 按月统计
        if leave_type == 'sick':
            sick_limit = float(sys_config.get('sickLeaveDays', 1))
            # 统计本月已批准的病假
            m_start, m_end = get_month_range(start_date.strftime('%Y-%m'))
            used_sick = db.session.query(func.sum(Leave.leave_days)).filter(
                Leave.emp_id == emp_id,
                Leave.leave_type == 'sick',
                Leave.approval_status == 'approved',
                Leave.start_date >= m_start,
                Leave.end_date <= m_end
            ).scalar() or 0
            
            if (float(used_sick) + leave_days) > sick_limit:
                return api_response(400, f"本月带薪病假额度不足。剩余: {sick_limit - float(used_sick)} 天")

        # 创建请假记录
        new_leave = Leave(
            emp_id=emp_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            leave_days=leave_days,
            leave_half_day=(half_day if leave_days == 0.5 else None),
            remark=remark,
            approval_status='pending'
        )
        db.session.add(new_leave)
        db.session.commit()

        return api_response(200, "请假申请已提交，等待审批")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"申请失败: {str(e)}")

@leave_bp.route('/leave/balance', methods=['GET'])
@api_role_required(['employee', 'manager', 'admin'])
def get_leave_balance():
    """获取当前员工的假期余额"""
    emp_id = session.get('emp_id')
    sys_config = get_sys_config()
    
    # 年假
    annual_limit = float(sys_config.get('annualLeaveDays', 5))
    used_annual = db.session.query(func.sum(Leave.leave_days)).filter(
        Leave.emp_id == emp_id,
        Leave.leave_type == 'annual',
        Leave.approval_status == 'approved',
        Leave.start_date >= date(date.today().year, 1, 1)
    ).scalar() or 0
    
    # 病假
    sick_limit = float(sys_config.get('sickLeaveDays', 1))
    m_start, _ = get_month_range(date.today().strftime('%Y-%m'))
    used_sick = db.session.query(func.sum(Leave.leave_days)).filter(
        Leave.emp_id == emp_id,
        Leave.leave_type == 'sick',
        Leave.approval_status == 'approved',
        Leave.start_date >= m_start
    ).scalar() or 0
    
    return api_response(200, "获取成功", {
        "annual": {"limit": annual_limit, "used": float(used_annual), "remaining": annual_limit - float(used_annual)},
        "sick": {"limit": sick_limit, "used": float(used_sick), "remaining": sick_limit - float(used_sick)},
        "notice_hours": int(sys_config.get('leaveApplyNotice', 24))
    })

@leave_bp.route('/leave/my-history', methods=['GET'])
@api_role_required(['employee', 'manager', 'admin'])
def get_my_leave_history():
    """获取当前登录员工的所有请假记录"""
    try:
        _ensure_leave_schema()
        emp_id = session.get('emp_id')
        leaves = Leave.query.filter_by(emp_id=emp_id).order_by(Leave.create_time.desc()).all()
        
        data = []
        for l in leaves:
            data.append({
                "leave_id": l.leave_id,
                "leave_type": l.leave_type,
                "start_date": l.start_date.strftime('%Y-%m-%d'),
                "end_date": l.end_date.strftime('%Y-%m-%d'),
                "leave_days": l.leave_days,
                "half_day": getattr(l, 'leave_half_day', None),
                "remark": l.remark,
                "approval_remark": getattr(l, 'approval_remark', None),
                "approval_status": l.approval_status,
                "create_time": l.create_time.strftime('%Y-%m-%d %H:%M')
            })
            
        return api_response(200, "获取成功", data)
    except Exception as e:
        return api_response(500, str(e))
