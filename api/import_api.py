from flask import Blueprint, request, jsonify, session, current_app
from models import db, Attendance, Employee, Department, ImportLog, User, SystemConfig, AbnormalAttendance, AbnormalTypeEnum
from datetime import datetime
import pandas as pd
import json
import random
from utils.attendance_calc import calculate_attendance_status
from utils.import_helpers import (
    get_system_config, find_best_match, read_uploaded_file, read_uploaded_file_headers,
    get_column_mapping, parse_attendance_row, parse_time_config
)

import_bp = Blueprint('import_api', __name__)

@import_bp.route('/import/analyze', methods=['POST'])
def analyze_file():
    """解析上传文件，返回列名和建议映射"""
    # 验证登录
    username = session.get('username')
    if not username:
        return jsonify({'code': 401, 'msg': '未登录'}), 401
    
    # 获取文件
    if 'file' not in request.files:
        return jsonify({'code': 400, 'msg': '未上传文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'msg': '文件名为空'}), 400

    try:
        # 读取文件列名
        try:
            columns = read_uploaded_file_headers(file)
        except ValueError as e:
            return jsonify({'code': 400, 'msg': str(e)}), 400
        
        # 计算建议映射
        mapping = {}
        mapping['name'] = find_best_match(columns, 'name', ['姓名', '员工姓名', 'User', 'Name', 'UserName'], None)
        mapping['dept'] = find_best_match(columns, 'dept', ['部门', '所属部门', 'Dept', 'Department'], None)
        mapping['check_in'] = find_best_match(columns, 'check_in', ['上班打卡时间', '上班打卡', '签到时间', '签到', 'CheckIn', 'StartTime'], None)
        mapping['check_out'] = find_best_match(columns, 'check_out', ['下班打卡时间', '下班打卡', '签退时间', '签退', 'CheckOut', 'EndTime'], None)
        mapping['abnormal_flag'] = find_best_match(columns, 'abnormal_flag', ['异常标识', '状态', 'Status', 'Flag'], None)
        
        return jsonify({
            'code': 200,
            'msg': '解析成功',
            'data': {
                'columns': columns,
                'mapping': mapping
            }
        })
    except Exception as e:
        error_msg = str(e)
        if "Excel file format cannot be determined" in error_msg or "Worksheet named" in error_msg:
             return jsonify({'code': 500, 'msg': '无法识别文件格式，请确保上传的是有效的 Excel 或 CSV 文件'}), 500
        return jsonify({'code': 500, 'msg': f'文件解析失败: {error_msg}'}), 500

@import_bp.route('/import/attendance', methods=['POST'])
def import_attendance():
    # 1. 验证用户登录
    username = session.get('username')
    if not username:
        return jsonify({'code': 401, 'msg': '未登录'}), 401
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'code': 401, 'msg': '用户不存在'}), 401

    # 2. 获取文件
    if 'file' not in request.files:
        return jsonify({'code': 400, 'msg': '未上传文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'msg': '文件名为空'}), 400

    # 3. 获取映射参数
    map_name = request.form.get('name')
    map_dept = request.form.get('dept')
    map_check_in = request.form.get('check_in')
    map_check_out = request.form.get('check_out')
    map_abnormal_flag = request.form.get('abnormal_flag')
    
    # 4. 初始化日志
    # 生成唯一 batch_id，加入毫秒或随机数防止冲突
    batch_id = datetime.now().strftime('%Y%m%d%H%M%S') + f"{user.user_id}{random.randint(100, 999)}"
    log = ImportLog(
        import_batch=batch_id,
        import_user_id=user.user_id,
        file_name=file.filename,
        file_size=0, 
        import_status='processing'
    )
    db.session.add(log)
    db.session.commit()

    try:
        # 5. 读取文件
        df = read_uploaded_file(file)
        
        # approximate size
        file.seek(0, 2)
        log.file_size = file.tell()
        file.seek(0)
        
        log.total_rows = len(df)
        
        success_count = 0
        fail_count = 0
        errors = []
        
        # 缓存现有数据
        employees = {e.emp_name: e for e in Employee.query.all()}
        departments = {d.dept_name: d for d in Department.query.all()}
        
        # 检查必要的列是否存在
        columns = df.columns.tolist()
        
        # 加载系统配置
        sys_config = get_system_config()
        time_config = parse_time_config(sys_config)

        columns = df.columns.tolist()
        mapping = get_column_mapping(columns, map_name, map_dept, map_check_in, map_check_out, map_abnormal_flag)
        map_name = mapping['name']
        map_dept = mapping['dept']
        map_check_in = mapping['check_in']
        map_check_out = mapping['check_out']
        map_abnormal_flag = mapping['abnormal_flag']

        create_new = request.form.get('create_new')

        if create_new is None:
            file_emps = set()
            file_depts = set()

            for _, row in df.iterrows():
                try:
                    parsed = parse_attendance_row(row, mapping)
                    if parsed is None:
                        continue
                    file_emps.add(parsed['emp_name'])
                    file_depts.add(parsed['dept_name'])
                except (ValueError, Exception):
                    continue

            db_emps = {e.emp_name for e in Employee.query.all()}
            db_depts = {d.dept_name for d in Department.query.all()}

            new_emps = list(file_emps - db_emps)
            new_depts = list(file_depts - db_depts)

            if new_emps or new_depts:
                db.session.delete(log)
                db.session.commit()
                return jsonify({
                    'code': 202,
                    'msg': '发现新数据，需确认',
                    'data': {
                        'new_employees': new_emps[:5],
                        'new_departments': new_depts[:5],
                        'new_emp_count': len(new_emps),
                        'new_dept_count': len(new_depts)
                    }
                }), 202
        
        # 确定是否创建新数据
        should_create = (create_new == 'true')
        skipped_rows = 0

        for index, row in df.iterrows():
            try:
                parsed = parse_attendance_row(row, mapping)
                if parsed is None:
                    continue

                emp_name = parsed['emp_name']
                dept_name = parsed['dept_name']
                att_date = parsed['att_date']
                check_in_dt = parsed['check_in_dt']
                check_out_dt = parsed['check_out_dt']
                flag_val = parsed['flag_val']

                dept_id = None
                if dept_name not in departments:
                    if not should_create:
                        skipped_rows += 1
                        continue
                    new_dept = Department(dept_name=dept_name, dept_code=f"D{len(departments) + 1:03d}")
                    db.session.add(new_dept)
                    db.session.flush()
                    departments[dept_name] = new_dept
                dept_id = departments[dept_name].dept_id

                if emp_name not in employees:
                    if not should_create:
                        skipped_rows += 1
                        continue
                    new_emp = Employee(emp_code=f"TMP{len(employees) + 1:04d}", emp_name=emp_name,
                                       dept_id=dept_id, entry_time=att_date)
                    db.session.add(new_emp)
                    db.session.flush()
                    employees[emp_name] = new_emp

                emp = employees[emp_name]
                if not emp.dept_id and dept_id:
                    emp.dept_id = dept_id

                att_record = Attendance.query.filter_by(emp_id=emp.emp_id, att_date=att_date).first()
                if not att_record:
                    att_record = Attendance(emp_id=emp.emp_id, att_date=att_date, import_batch=batch_id)
                    db.session.add(att_record)

                if check_in_dt is not None and not pd.isna(check_in_dt):
                    att_record.check_in_time = check_in_dt
                if check_out_dt is not None and not pd.isna(check_out_dt):
                    att_record.check_out_time = check_out_dt

                calculate_attendance_status(att_record, sys_config, manual_flag=flag_val)
                success_count += 1
                
            except Exception as e:
                fail_count += 1
                errors.append(f"Row {index+2}: {str(e)}")
        
        # 更新日志
        log.success_rows = success_count
        log.fail_rows = fail_count
        log.import_status = 'success' if fail_count == 0 else 'success_with_errors'
        if fail_count == log.total_rows and log.total_rows > 0:
            log.import_status = 'failed'
        
        if errors:
            # 只保存前20个错误
            log.fail_reason = json.dumps(errors[:20], ensure_ascii=False)
            
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'msg': '导入完成',
            'data': {
                'success': success_count,
                'fail': fail_count,
                'skipped': skipped_rows,
                'errors': errors[:5]
            }
        })
        
    except Exception as e:
        db.session.rollback()
        log.import_status = 'failed'
        log.fail_reason = str(e)
        db.session.commit()
        
        msg = str(e)
        if "Excel file format cannot be determined" in msg:
            msg = '无法识别文件格式，请确保上传的是有效的 Excel 或 CSV 文件'
        elif "Worksheet named" in msg:
            msg = '无法读取工作表，文件可能已损坏'
            
        return jsonify({'code': 500, 'msg': f'系统错误: {msg}'}), 500
