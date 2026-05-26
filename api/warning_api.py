from flask import Blueprint, request, jsonify
from models import db, Employee, SystemConfig
from utils.email_utils import send_attendance_email
from utils.decorators import api_role_required
from utils.api_helpers import get_month_range
from api.dashboard_api import get_warning_list
from datetime import datetime

warning_bp = Blueprint('warning_api', __name__)

@warning_bp.route('/warning/send-email', methods=['POST'])
@api_role_required(['admin'])
def send_warning_email():
    """发送单个员工预警邮件"""
    data = request.json
    emp_id = data.get('emp_id')
    w_type = data.get('type')
    count = data.get('count')

    if not all([emp_id, w_type, count]):
        return jsonify({"code": 400, "msg": "参数缺失"}), 400

    emp = Employee.query.get(emp_id)
    if not emp or not emp.email:
        return jsonify({"code": 404, "msg": "员工不存在或未配置邮箱"}), 404

    subject = f"【考勤预警】{emp.emp_name}，您本月的考勤存在异常"
    content = f"""
尊敬的 {emp.emp_name}：

系统监测到您本月的考勤存在异常情况：
异常类型：{w_type}
当前累计：{count} 次

请及时关注并按公司规定处理。如有疑问，请咨询人力资源部。

此邮件由考勤系统自动发出，请勿直接回复。
    """
    
    success, msg = send_attendance_email(emp.email, subject, content)
    if success:
        return jsonify({"code": 200, "msg": "发送成功"})
    else:
        return jsonify({"code": 500, "msg": f"发送失败: {msg}"}), 500

@warning_bp.route('/warning/send-email-batch', methods=['POST'])
@api_role_required(['admin'])
def send_batch_warning_emails():
    """给选定的预警员工批量发邮件"""
    try:
        data = request.json
        warnings = data.get('warnings', [])
        
        if not warnings:
            return jsonify({"code": 400, "msg": "未选择任何员工"}), 400

        success_count = 0
        fail_count = 0
        
        for w in warnings:
            emp_id = w.get('emp_id')
            w_type = w.get('type')
            count = w.get('count')
            
            emp = Employee.query.get(emp_id)
            if emp and emp.email:
                subject = f"【考勤预警】{emp.emp_name}，您本月的考勤存在异常"
                content = f"""
尊敬的 {emp.emp_name}：

系统监测到您本月的考勤存在异常情况：
异常类型：{w_type}
当前累计：{count} 次

请及时关注并按公司规定处理。如有疑问，请咨询人力资源部。

此邮件由考勤系统自动发出，请勿直接回复。
                """
                success, _ = send_attendance_email(emp.email, subject, content)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            else:
                fail_count += 1

        return jsonify({
            "code": 200, 
            "msg": f"批量发送完成：成功 {success_count} 人，失败 {fail_count} 人"
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": f"批量发送失败: {str(e)}"}), 500

@warning_bp.route('/warning/send-email-all', methods=['POST'])
@api_role_required(['admin'])
def send_all_warning_emails():
    """给所有预警员工批量发邮件"""
    try:
        # 获取本月时间范围
        month_str = datetime.now().strftime('%Y-%m')
        start_date, end_date = get_month_range(month_str)
        
        # 获取配置
        sys_config = {c.config_key: c.config_value for c in SystemConfig.query.all()}
        
        # 获取预警名单
        warnings = get_warning_list(start_date, end_date, sys_config)
        
        if not warnings:
            return jsonify({"code": 200, "msg": "当前没有需要预警的员工"})

        success_count = 0
        fail_count = 0
        
        for w in warnings:
            emp = Employee.query.get(w['emp_id'])
            if emp and emp.email:
                subject = f"【考勤预警】{emp.emp_name}，您本月的考勤存在异常"
                content = f"""
尊敬的 {emp.emp_name}：

系统监测到您本月的考勤存在异常情况：
异常类型：{w['type']}
当前累计：{w['count']} 次

请及时关注并按公司规定处理。如有疑问，请咨询人力资源部。

此邮件由考勤系统自动发出，请勿直接回复。
                """
                success, _ = send_attendance_email(emp.email, subject, content)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            else:
                fail_count += 1

        return jsonify({
            "code": 200, 
            "msg": f"批量发送完成：成功 {success_count} 人，失败 {fail_count} 人"
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": f"批量发送失败: {str(e)}"}), 500
