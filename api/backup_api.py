from flask import Blueprint, jsonify, request, send_file, current_app
import os
import json
import shutil
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from models import db, User, Employee, Department, Attendance, AbnormalAttendance, SystemConfig, Leave, HolidayCalendar
from utils.decorators import api_role_required

backup_bp = Blueprint('backup_api', __name__)

BACKUP_DIR = 'backups'

def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

def get_safe_backup_path(filename):
    if not filename or filename != os.path.basename(filename):
        raise ValueError('invalid filename')
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise ValueError('invalid filename')
    if not filename.endswith('.json'):
        raise ValueError('only .json is allowed')

    backup_root = os.path.abspath(BACKUP_DIR)
    file_path = os.path.abspath(os.path.join(BACKUP_DIR, filename))
    if os.path.commonpath([backup_root, file_path]) != backup_root:
        raise ValueError('invalid file path')
    return file_path

def get_file_size(file_path):
    size_bytes = os.path.getsize(file_path)
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

@backup_bp.route('/backups/list', methods=['GET'])
@api_role_required(["admin"])
def get_backup_list():
    ensure_backup_dir()
    backups = []
    try:
        files = os.listdir(BACKUP_DIR)
        # 按修改时间倒序排列
        files.sort(key=lambda x: os.path.getmtime(os.path.join(BACKUP_DIR, x)), reverse=True)
        
        for filename in files:
            if not filename.endswith('.json'):
                continue
                
            file_path = os.path.join(BACKUP_DIR, filename)
            timestamp = os.path.getmtime(file_path)
            backup_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            # 解析文件名获取类型 (格式: backup_type_timestamp.json)
            # 例如: manual_20250101120000.json
            parts = filename.split('_')
            backup_type = '自动备份'
            if len(parts) > 0:
                if parts[0] == 'manual':
                    backup_type = '手动备份'
                elif parts[0] == 'auto':
                    backup_type = '自动备份'
            
            backups.append({
                'id': filename,
                'filename': filename,
                'time': backup_time,
                'size': get_file_size(file_path),
                'type': backup_type,
                'status': '已完成' # 暂时都是已完成，因为文件存在就是完成了
            })
            
        return jsonify({'code': 200, 'msg': '获取成功', 'data': backups})
    except Exception as e:
        return jsonify({'code': 500, 'msg': f'获取备份列表失败: {str(e)}'})

def generate_backup_file(backup_type='manual'):
    """生成备份文件核心逻辑"""
    ensure_backup_dir()
    
    # 收集所有数据
    leaves_data = []
    try:
        leaves_data = [{
            'leave_id': l.leave_id, 'emp_id': l.emp_id, 'leave_type': l.leave_type,
            'start_date': l.start_date.isoformat() if l.start_date else None,
            'end_date': l.end_date.isoformat() if l.end_date else None,
            'leave_days': float(l.leave_days) if l.leave_days is not None else None,
            'leave_half_day': getattr(l, 'leave_half_day', None),
            'approval_status': l.approval_status, 'approver_id': l.approver_id,
            'remark': l.remark,
            'create_time': l.create_time.isoformat() if l.create_time else None,
            'update_time': l.update_time.isoformat() if l.update_time else None
        } for l in Leave.query.all()]
    except Exception as e:
        current_app.logger.warning(f"Skip leaves backup: {e}")
        leaves_data = []

    holiday_calendar_data = []
    try:
        holiday_calendar_data = [{
            'holiday_date': h.holiday_date.isoformat() if h.holiday_date else None,
            'is_workday': int(h.is_workday or 0),
            'name': h.name,
            'create_time': h.create_time.isoformat() if h.create_time else None,
            'update_time': h.update_time.isoformat() if h.update_time else None
        } for h in HolidayCalendar.query.all()]
    except Exception as e:
        current_app.logger.warning(f"Skip holiday calendar backup: {e}")
        holiday_calendar_data = []

    data = {
        'departments': [{
            'dept_id': d.dept_id, 'dept_name': d.dept_name, 'dept_code': d.dept_code,
            'parent_dept_id': d.parent_dept_id, 'manager_id': d.manager_id, 'status': d.status,
            'create_time': d.create_time.isoformat() if d.create_time else None
        } for d in Department.query.all()],
        
        'employees': [{
            'emp_id': e.emp_id, 'emp_code': e.emp_code, 'emp_name': e.emp_name,
            'dept_id': e.dept_id, 'phone': e.phone, 'email': e.email,
            'entry_time': e.entry_time.isoformat() if e.entry_time else None,
            'status': e.status, 'create_time': e.create_time.isoformat() if e.create_time else None
        } for e in Employee.query.all()],
        
        'users': [{
            'user_id': u.user_id, 'username': u.username, 'password_hash': u.password,
            'emp_id': u.emp_id, 'role': u.role, 'status': u.status,
            'last_login_time': u.last_login_time.isoformat() if u.last_login_time else None,
            'create_time': u.create_time.isoformat() if u.create_time else None
        } for u in User.query.all()],
        
        'leaves': leaves_data,
        'holiday_calendar': holiday_calendar_data,
        
        'attendances': [{
            'att_id': a.att_id, 'emp_id': a.emp_id, 'att_date': a.att_date.isoformat() if a.att_date else None,
            'check_in_time': a.check_in_time.isoformat() if a.check_in_time else None,
            'check_out_time': a.check_out_time.isoformat() if a.check_out_time else None,
            'work_duration': a.work_duration, 'late_minutes': a.late_minutes, 'early_minutes': a.early_minutes,
            'is_absent': a.is_absent, 'import_batch': a.import_batch,
            'create_time': a.create_time.isoformat() if a.create_time else None
        } for a in Attendance.query.all()],
        
        'abnormal_attendances': [{
            'abnormal_id': aa.abnormal_id, 'emp_id': aa.emp_id, 'abnormal_date': aa.abnormal_date.isoformat() if aa.abnormal_date else None,
            'abnormal_type': aa.abnormal_type.value,
            'abnormal_desc': aa.abnormal_desc, 'is_processed': aa.is_processed, 'processor_id': aa.processor_id,
            'process_remark': aa.process_remark,
            'create_time': aa.create_time.isoformat() if aa.create_time else None
        } for aa in AbnormalAttendance.query.all()],
        
        'system_configs': [{
            'config_id': sc.config_id, 'config_key': sc.config_key, 'config_value': sc.config_value,
            'config_desc': sc.config_desc, 'config_type': sc.config_type,
            'update_time': sc.update_time.isoformat() if sc.update_time else None
        } for sc in SystemConfig.query.all()]
    }
    
    # 2. 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"{backup_type}_{timestamp}.json"
    file_path = os.path.join(BACKUP_DIR, filename)
    
    # 3. 写入文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    return filename

def clean_old_backups(retention_days=30):
    """清理旧备份"""
    ensure_backup_dir()
    now = datetime.now()
    try:
        files = os.listdir(BACKUP_DIR)
        deleted_count = 0
        for filename in files:
            if not filename.endswith('.json'):
                continue
                
            file_path = os.path.join(BACKUP_DIR, filename)
            # 获取文件修改时间
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            # 计算时间差
            diff = now - file_mtime
            if diff.days > retention_days:
                os.remove(file_path)
                deleted_count += 1
                
        current_app.logger.info(f"Cleaned up {deleted_count} old backups.")
    except Exception as e:
        current_app.logger.error(f"Cleanup failed: {e}")

def perform_auto_backup():
    """执行自动备份任务"""
    # 注意：此函数需要在应用上下文中运行
    try:
        current_app.logger.info(f"Starting auto backup at {datetime.now()}...")
        filename = generate_backup_file(backup_type='auto')
        current_app.logger.info(f"Auto backup created: {filename}")
        
        clean_old_backups(retention_days=30)
    except Exception as e:
        current_app.logger.error(f"Auto backup failed: {e}")

@backup_bp.route('/backups/create', methods=['POST'])
@api_role_required(["admin"])
def create_backup():
    try:
        filename = generate_backup_file(backup_type='manual')
        return jsonify({'code': 200, 'msg': '备份成功', 'data': {'filename': filename}})
    except Exception as e:
        return jsonify({'code': 500, 'msg': f'备份失败: {str(e)}'})

@backup_bp.route('/backups/restore', methods=['POST'])
@api_role_required(["admin"])
def restore_backup():
    ensure_backup_dir()
    try:
        data = request.get_json()
        filename = data.get('filename')
        if not filename:
            return jsonify({'code': 400, 'msg': '缺少文件名参数'})
            
        file_path = get_safe_backup_path(filename)
        if not os.path.exists(file_path):
            return jsonify({'code': 404, 'msg': '备份文件不存在'})
            
        # 读取备份文件
        with open(file_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
            
        # 恢复数据 (需要谨慎处理，通常需要先清空表或使用upsert)
        # 这里采用清空后插入的策略 (简单粗暴但有效)
        # 注意外键约束，需要按顺序删除和插入
        
        # 1. 清空现有数据 (顺序：异常考勤 -> 考勤 -> 用户 -> 请假 -> 员工 -> 部门 -> 节假日 -> 配置)
        # 注意：User 和 Employee 有相互依赖 (User.emp_id -> Employee.emp_id)，Department.manager_id -> Employee.emp_id
        # Employee.dept_id -> Department.dept_id
        # 这是一个循环依赖。
        # 删除顺序：AbnormalAttendance, Attendance, User, Employee, Department, SystemConfig
        # 但是 Employee 依赖 Department (dept_id), Department 依赖 Employee (manager_id)
        # 删除时，只要外键是 nullable 的，可以先置空再删除，或者禁用外键检查。
        # SQLite 默认开启外键支持，但 Flask-SQLAlchemy 可能会处理。
        # 最简单的方法是禁用外键检查，清空，插入，启用。
        
        # MySQL: SET FOREIGN_KEY_CHECKS = 0;
        db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 0;"))
        
        AbnormalAttendance.query.delete()
        Attendance.query.delete()
        User.query.delete()
        try:
            Leave.query.delete()
        except Exception:
            pass
        Employee.query.delete()
        Department.query.delete()
        try:
            HolidayCalendar.query.delete()
        except Exception:
            pass
        SystemConfig.query.delete()
        
        db.session.flush() # 确保删除操作在插入前执行（在同一事务中）
        
        # 2. 插入数据
        # 节假日
        for h in backup_data.get('holiday_calendar', []):
            try:
                holiday_date = datetime.fromisoformat(h['holiday_date']).date() if h.get('holiday_date') else None
            except Exception:
                holiday_date = None
            if not holiday_date:
                continue
            rec = HolidayCalendar(
                holiday_date=holiday_date,
                is_workday=h.get('is_workday', 0),
                name=h.get('name')
            )
            if h.get('create_time'):
                rec.create_time = datetime.fromisoformat(h['create_time'])
            if h.get('update_time'):
                rec.update_time = datetime.fromisoformat(h['update_time'])
            db.session.add(rec)
        db.session.flush()

        # 部门
        for d in backup_data.get('departments', []):
            dept = Department(
                dept_id=d['dept_id'], dept_name=d['dept_name'], dept_code=d['dept_code'],
                parent_dept_id=d['parent_dept_id'], manager_id=d['manager_id'], status=d['status']
            )
            if d['create_time']: dept.create_time = datetime.fromisoformat(d['create_time'])
            db.session.add(dept)
        db.session.flush() # 阶段性flush，定位错误
            
        # 员工
        for e in backup_data.get('employees', []):
            emp = Employee(
                emp_id=e['emp_id'], emp_code=e['emp_code'], emp_name=e['emp_name'],
                dept_id=e['dept_id'], phone=e['phone'], email=e['email'], status=e['status']
            )
            if e['entry_time']: emp.entry_time = datetime.fromisoformat(e['entry_time']).date()
            if e['create_time']: emp.create_time = datetime.fromisoformat(e['create_time'])
            db.session.add(emp)
        db.session.flush()
            
        # 用户
        for u in backup_data.get('users', []):
            user = User(
                user_id=u['user_id'], username=u['username'],
                emp_id=u['emp_id'], role=u['role'], status=u['status']
            )
            # 直接设置加密后的密码，避免再次加密
            user.password = u['password_hash']
            if u['last_login_time']: user.last_login_time = datetime.fromisoformat(u['last_login_time'])
            if u['create_time']: user.create_time = datetime.fromisoformat(u['create_time'])
            db.session.add(user)
        db.session.flush()

        # 请假
        for l in backup_data.get('leaves', []):
            leave = Leave(
                leave_id=l.get('leave_id'),
                emp_id=l.get('emp_id'),
                leave_type=l.get('leave_type'),
                leave_days=l.get('leave_days') if l.get('leave_days') is not None else 0,
                approval_status=l.get('approval_status'),
                approver_id=l.get('approver_id'),
                remark=l.get('remark')
            )
            if l.get('start_date'):
                leave.start_date = datetime.fromisoformat(l['start_date']).date()
            if l.get('end_date'):
                leave.end_date = datetime.fromisoformat(l['end_date']).date()
            if hasattr(leave, 'leave_half_day'):
                leave.leave_half_day = l.get('leave_half_day')
            if l.get('create_time'):
                leave.create_time = datetime.fromisoformat(l['create_time'])
            if l.get('update_time'):
                leave.update_time = datetime.fromisoformat(l['update_time'])
            db.session.add(leave)
        db.session.flush()
            
        # 考勤
        for a in backup_data.get('attendances', []):
            att = Attendance(
                att_id=a['att_id'], emp_id=a['emp_id'], work_duration=a['work_duration'],
                late_minutes=a['late_minutes'], early_minutes=a['early_minutes'],
                is_absent=a['is_absent'], import_batch=a.get('import_batch')
            )
            if a['att_date']: att.att_date = datetime.fromisoformat(a['att_date']).date()
            if a['check_in_time']: att.check_in_time = datetime.fromisoformat(a['check_in_time'])
            if a['check_out_time']: att.check_out_time = datetime.fromisoformat(a['check_out_time'])
            if a.get('create_time'): att.create_time = datetime.fromisoformat(a['create_time'])
            db.session.add(att)
        db.session.flush()
            
        # 异常考勤
        for aa in backup_data.get('abnormal_attendances', []):
            abn = AbnormalAttendance(
                abnormal_id=aa['abnormal_id'], emp_id=aa['emp_id'], abnormal_type=aa['abnormal_type'],
                abnormal_desc=aa['abnormal_desc'],
                is_processed=aa['is_processed'], processor_id=aa.get('processor_id'),
                process_remark=aa.get('process_remark')
            )
            if aa['abnormal_date']: abn.abnormal_date = datetime.fromisoformat(aa['abnormal_date']).date()
            if aa.get('create_time'): abn.create_time = datetime.fromisoformat(aa['create_time'])
            db.session.add(abn)
        db.session.flush()
            
        # 系统配置
        for sc in backup_data.get('system_configs', []):
            conf = SystemConfig(
                config_id=sc['config_id'], config_key=sc['config_key'], config_value=sc['config_value'],
                config_desc=sc['config_desc'], config_type=sc['config_type']
            )
            if sc['update_time']: conf.update_time = datetime.fromisoformat(sc['update_time'])
            db.session.add(conf)
        db.session.flush()
            
        db.session.commit()
        db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1;"))
        
        return jsonify({'code': 200, 'msg': '恢复成功'})
        
    except IntegrityError as e:
        db.session.rollback()
        try:
            db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1;"))
        except:
            pass
        
        error_msg = str(e.orig) if e.orig else str(e)
        # 截断过长的错误信息
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
            
        return jsonify({'code': 500, 'msg': f'数据库完整性错误: {error_msg}'})
        
    except Exception as e:
        db.session.rollback()
        # 尝试恢复外键检查
        try:
            db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1;"))
        except:
            pass
        return jsonify({'code': 500, 'msg': f'恢复失败: {str(e)[:200]}'})

@backup_bp.route('/backups/delete', methods=['POST'])
@api_role_required(["admin"])
def delete_backup():
    ensure_backup_dir()
    try:
        data = request.get_json()
        filename = data.get('filename')
        if not filename:
            return jsonify({'code': 400, 'msg': '缺少文件名参数'})
            
        file_path = get_safe_backup_path(filename)
        if not os.path.exists(file_path):
            return jsonify({'code': 404, 'msg': '备份文件不存在'})
            
        os.remove(file_path)
        return jsonify({'code': 200, 'msg': '删除成功'})
        
    except Exception as e:
        return jsonify({'code': 500, 'msg': f'删除失败: {str(e)}'})

@backup_bp.route('/backups/download/<filename>', methods=['GET'])
@api_role_required(["admin"])
def download_backup(filename):
    ensure_backup_dir()
    try:
        file_path = get_safe_backup_path(filename)
    except ValueError as e:
        return jsonify({'code': 400, 'msg': str(e)}), 400
    if not os.path.exists(file_path):
        return jsonify({'code': 404, 'msg': '备份文件不存在'}), 404
        
    return send_file(file_path, as_attachment=True, download_name=filename)
