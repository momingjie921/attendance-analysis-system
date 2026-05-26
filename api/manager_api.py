from flask import Blueprint, jsonify, session, request
from models import db, Employee, Attendance, AbnormalAttendance, Department, AbnormalTypeEnum
from sqlalchemy import func, and_, case, or_
from datetime import datetime, date, timedelta
from utils.decorators import api_role_required
from utils.api_helpers import api_response, get_month_range, ABNORMAL_TYPE_CN, get_working_days, get_working_dates
import pandas as pd
import json
import random
from models import ImportLog, User, SystemConfig
from utils.attendance_calc import calculate_attendance_status
from utils.import_helpers import (
    get_system_config, find_best_match, read_uploaded_file, read_uploaded_file_headers,
    get_column_mapping, parse_attendance_row, parse_time_config
)

manager_bp = Blueprint('manager_api', __name__)

def get_descendant_dept_ids(root_dept_id: int):
    seen = set()
    frontier = [root_dept_id]
    while frontier:
        rows = Department.query.filter(
            Department.parent_dept_id.in_(frontier),
            Department.status == 1
        ).with_entities(Department.dept_id).all()
        next_frontier = []
        for (dept_id,) in rows:
            if dept_id not in seen:
                seen.add(dept_id)
                next_frontier.append(dept_id)
        frontier = next_frontier
    return list(seen)

@manager_bp.route('/manager/import/analyze', methods=['POST'])
@api_role_required(['manager'])
def analyze_file():
    """解析上传文件，返回列名和建议映射"""
    # 1. 获取文件
    if 'file' not in request.files:
        return api_response(400, '未上传文件')
    file = request.files['file']
    if file.filename == '':
        return api_response(400, '文件名为空')

    try:
        try:
            columns = read_uploaded_file_headers(file)
        except ValueError as e:
            return api_response(400, str(e))
        
        # 3. 计算建议映射
        mapping = {}
        mapping['name'] = find_best_match(columns, 'name', ['姓名', '员工姓名', 'User', 'Name', 'UserName'], None)
        mapping['dept'] = find_best_match(columns, 'dept', ['部门', '所属部门', 'Dept', 'Department'], None)
        mapping['check_in'] = find_best_match(columns, 'check_in', ['上班打卡时间', '上班打卡', '签到时间', '签到', 'CheckIn', 'StartTime'], None)
        mapping['check_out'] = find_best_match(columns, 'check_out', ['下班打卡时间', '下班打卡', '签退时间', '签退', 'CheckOut', 'EndTime'], None)
        mapping['abnormal_flag'] = find_best_match(columns, 'abnormal_flag', ['异常标识', '状态', 'Status', 'Flag'], None)
        
        return api_response(200, '解析成功', {
            'columns': columns,
            'mapping': mapping
        })
    except Exception as e:
        error_msg = str(e)
        if "Excel file format cannot be determined" in error_msg or "Worksheet named" in error_msg:
             return api_response(500, '无法识别文件格式，请确保上传的是有效的 Excel 或 CSV 文件')
        return api_response(500, f'文件解析失败: {error_msg}')

@manager_bp.route('/manager/import/attendance', methods=['POST'])
@api_role_required(['manager'])
def import_attendance():
    """部门经理导入考勤数据"""
    try:
        username = session.get('username')
        user = Employee.query.join(Employee.user).filter_by(username=username).first()
        dept_id = user.dept_id
        
        # 获取当前用户的 User 实体，用于记录日志
        current_user = User.query.filter_by(username=username).first()

        # 2. 获取文件
        if 'file' not in request.files:
            return api_response(400, '未上传文件')
        file = request.files['file']
        if file.filename == '':
            return api_response(400, '文件名为空')

        # 3. 获取映射参数
        map_name = request.form.get('name')
        map_dept = request.form.get('dept')
        map_check_in = request.form.get('check_in')
        map_check_out = request.form.get('check_out')
        map_abnormal_flag = request.form.get('abnormal_flag')
        
        # 4. 初始化日志
        batch_id = datetime.now().strftime('%Y%m%d%H%M%S') + f"{current_user.user_id}{random.randint(100, 999)}"
        log = ImportLog(
            import_batch=batch_id,
            import_user_id=current_user.user_id,
            file_name=file.filename,
            file_size=0, 
            import_status='processing'
        )
        db.session.add(log)
        db.session.commit()

        # 5. 读取文件
        df = read_uploaded_file(file)

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

        sys_config = get_system_config()
        time_config = parse_time_config(sys_config)

        columns = df.columns.tolist()
        mapping = get_column_mapping(columns, map_name, map_dept, map_check_in, map_check_out, map_abnormal_flag)
        map_name = mapping['name']
        map_dept = mapping['dept']
        map_check_in = mapping['check_in']
        map_check_out = mapping['check_out']
        map_abnormal_flag = mapping['abnormal_flag']

        allowed_depts = Department.query.filter(
            Department.dept_id == dept_id, Department.status == 1
        ).with_entities(Department.dept_name).all()
        allowed_depts_set = {name for (name,) in allowed_depts}

        skipped_rows = 0
        create_new = request.form.get('create_new')
        should_create = (create_new == 'true')

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

                if dept_name not in allowed_depts_set:
                    raise ValueError(f"无权导入部门: {dept_name}")

                if emp_name not in employees and not should_create:
                    skipped_rows += 1
                    continue

                with db.session.begin_nested():
                    if emp_name not in employees:
                        target_dept = departments.get(dept_name)
                        if not target_dept:
                            raise ValueError(f"部门不存在且无权创建: {dept_name}")
                        suffix = str(batch_id)[-6:]
                        emp_code = f"IMP{suffix}{index + 1:04d}"
                        new_emp = Employee(emp_code=emp_code, emp_name=emp_name,
                                           dept_id=target_dept.dept_id, entry_time=att_date)
                        db.session.add(new_emp)
                        db.session.flush()
                        employees[emp_name] = new_emp

                    emp = employees[emp_name]
                    if emp.department.dept_name != dept_name:
                        raise ValueError(f"员工 {emp_name} 所属部门({emp.department.dept_name})与文件({dept_name})不符")

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
        
        log.success_rows = success_count
        log.fail_rows = fail_count
        log.import_status = 'success' if fail_count == 0 else 'success_with_errors'
        if fail_count == log.total_rows and log.total_rows > 0:
            log.import_status = 'failed'
        
        if errors:
            log.fail_reason = json.dumps(errors[:20], ensure_ascii=False)
            
        db.session.commit()
        
        return api_response(200, '导入完成', {
            'success': success_count,
            'fail': fail_count,
            'skipped': skipped_rows,
            'errors': errors[:5]
        })
        
    except Exception as e:
        db.session.rollback()
        # log.import_status = 'failed' # log may not be created if error before
        # log.fail_reason = str(e)
        # db.session.commit()
        return api_response(500, f"系统错误: {str(e)}")

@manager_bp.route('/manager/dashboard/data', methods=['GET'])
@api_role_required(['manager'])
def get_manager_dashboard_data():
    """获取部门经理仪表盘数据"""
    try:
        username = session.get('username')
        user = Employee.query.join(Employee.user).filter_by(username=username).first()
        if not user:
            return api_response(404, "未找到当前用户关联的员工信息")
            
        dept_id = user.dept_id
        
        # 获取请求的月份，默认当前月
        month_str = request.args.get('month', datetime.now().strftime('%Y-%m'))
        start_date, end_date = get_month_range(month_str)
        effective_end_date = min(end_date, date.today())
        if effective_end_date < start_date:
            effective_end_date = end_date
        
        metrics_emp_query = (
            Employee.query
            .outerjoin(Employee.user)
            .filter(
                Employee.dept_id == dept_id,
                Employee.status == 1,
                or_(
                    Employee.emp_id == user.emp_id,
                    User.role == 'employee',
                    User.user_id.is_(None)
                )
            )
        )
        managed_emp_query = (
            Employee.query
            .outerjoin(Employee.user)
            .filter(
                Employee.dept_id == dept_id,
                Employee.status == 1,
                Employee.emp_id != user.emp_id,
                or_(User.role == 'employee', User.user_id.is_(None))
            )
        )
        current_emp_count = metrics_emp_query.count()
        
        # 上月员工数对比
        last_month_start = (start_date - timedelta(days=1)).replace(day=1)
        # 这是一个估算，准确的历史人数需要历史记录表，这里简化处理：假设没有离职就是当前人数
        # 或者如果有 create_time，可以统计 entry_time <= last_month_end
        # 这里为了演示简单，暂时返回0或根据 entry_time 计算
        prev_emp_count = metrics_emp_query.filter(Employee.entry_time < start_date).count()
        emp_diff = current_emp_count - prev_emp_count
        
        dept_emp_ids_metrics = [e.emp_id for e in metrics_emp_query.all()]
        dept_emp_ids_managed = [e.emp_id for e in managed_emp_query.all()]
        
        if not dept_emp_ids_metrics:
            return api_response(200, "暂无数据", {})

        working_dates = get_working_dates(start_date, effective_end_date) if start_date <= effective_end_date else []
        month_days = len(working_dates)
        total_person_days = len(dept_emp_ids_metrics) * month_days
        
        attendance_count = 0
        if working_dates:
            attendance_count = Attendance.query.filter(
                Attendance.emp_id.in_(dept_emp_ids_metrics),
                Attendance.att_date.in_(working_dates),
                Attendance.is_absent == 0
            ).count()
        
        attendance_rate = round((attendance_count / total_person_days) * 100, 1) if total_person_days > 0 else 0
        
        # 上月出勤率
        last_month_end = start_date - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        last_working_dates = get_working_dates(last_month_start, last_month_end) if last_month_start <= last_month_end else []
        last_month_days = len(last_working_dates)
        last_total_person_days = len(dept_emp_ids_metrics) * last_month_days # 简化：假设人员不变
        
        last_attendance_count = 0
        if last_working_dates:
            last_attendance_count = Attendance.query.filter(
                Attendance.emp_id.in_(dept_emp_ids_metrics),
                Attendance.att_date.in_(last_working_dates),
                Attendance.is_absent == 0
            ).count()
        
        last_attendance_rate = round((last_attendance_count / last_total_person_days) * 100, 1) if last_total_person_days > 0 else 0
        rate_diff = round(attendance_rate - last_attendance_rate, 1)

        # 3. 本月异常次数
        abnormal_count = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id.in_(dept_emp_ids_metrics),
            AbnormalAttendance.abnormal_date.in_(working_dates) if working_dates else AbnormalAttendance.abnormal_date.between(start_date, end_date)
        ).count()
        
        last_abnormal_count = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id.in_(dept_emp_ids_metrics),
            AbnormalAttendance.abnormal_date.in_(last_working_dates) if last_working_dates else AbnormalAttendance.abnormal_date.between(last_month_start, last_month_end)
        ).count()
        
        abnormal_diff_percent = 0
        if last_abnormal_count > 0:
            abnormal_diff_percent = round(((abnormal_count - last_abnormal_count) / last_abnormal_count) * 100, 1)
        
        # 4. 平均迟到时长
        # 查找迟到记录 (LATE)
        late_records = Attendance.query.filter(
            Attendance.emp_id.in_(dept_emp_ids_metrics),
            Attendance.att_date.in_(working_dates) if working_dates else Attendance.att_date.between(start_date, end_date),
            Attendance.late_minutes > 0
        ).all()
        
        total_late_minutes = sum([r.late_minutes for r in late_records if r.late_minutes])
        avg_late_minutes = int(total_late_minutes / len(late_records)) if late_records else 0
        
        # 上月平均迟到
        last_late_records = Attendance.query.filter(
            Attendance.emp_id.in_(dept_emp_ids_metrics),
            Attendance.att_date.in_(last_working_dates) if last_working_dates else Attendance.att_date.between(last_month_start, last_month_end),
            Attendance.late_minutes > 0
        ).all()
        last_total_late = sum([r.late_minutes for r in last_late_records if r.late_minutes])
        last_avg_late = int(last_total_late / len(last_late_records)) if last_late_records else 0
        late_diff = avg_late_minutes - last_avg_late

        # 5. 员工出勤率排名 (Chart)
        # 计算每个员工的出勤率
        emp_ranks = []
        for eid in dept_emp_ids_managed:
            emp = Employee.query.get(eid)
            p_days = 0
            if working_dates:
                p_days = Attendance.query.filter(
                    Attendance.emp_id == eid,
                    Attendance.att_date.in_(working_dates),
                    Attendance.is_absent == 0
                ).count()
            rate = round((p_days / month_days) * 100, 1) if month_days > 0 else 0.0
            emp_ranks.append({'name': emp.emp_name, 'rate': rate})
        
        # 排序并取前8
        emp_ranks.sort(key=lambda x: x['rate'], reverse=True)
        top_emp_ranks = emp_ranks[:8]
        
        # 6. 异常类型分布 (Chart)
        abnormal_dist = db.session.query(
            AbnormalAttendance.abnormal_type,
            func.count(AbnormalAttendance.abnormal_id)
        ).filter(
            AbnormalAttendance.emp_id.in_(dept_emp_ids_metrics),
            AbnormalAttendance.abnormal_date.between(start_date, effective_end_date)
        ).group_by(AbnormalAttendance.abnormal_type).all()
        
        abnormal_pie_data = []
        for atype, count in abnormal_dist:
            abnormal_pie_data.append({
                'name': ABNORMAL_TYPE_CN.get(atype.value, atype.value),
                'value': count
            })
            
        # 7. 异常考勤明细 (Table - Top 5 or recent)
        recent_abnormals = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id.in_(dept_emp_ids_managed),
            AbnormalAttendance.abnormal_date.between(start_date, effective_end_date)
        ).order_by(AbnormalAttendance.abnormal_date.desc()).limit(10).all()
        
        abnormal_list = []
        for abn in recent_abnormals:
            # 获取时长 (迟到/早退)
            duration = "-"
            att = Attendance.query.filter_by(emp_id=abn.emp_id, att_date=abn.abnormal_date).first()
            if abn.abnormal_type == AbnormalTypeEnum.LATE and att and att.late_minutes:
                duration = str(att.late_minutes)
            elif abn.abnormal_type == AbnormalTypeEnum.EARLY and att and att.early_minutes:
                duration = str(att.early_minutes)
                
            # 状态处理 (Mock logic for now, or real if we add fields)
            status_text = "待处理"
            status_class = "badge-warning"
            if abn.is_processed:
                status_text = "已处理" # 默认
                status_class = "badge-success"
                # 这里可以根据 remark 进一步判断，如果 remark 包含 "警告" 则显示已警告
                if abn.process_remark and "警告" in abn.process_remark:
                    status_text = "已警告"
                    status_class = "badge-danger"
                elif abn.process_remark and "补假" in abn.process_remark:
                    status_text = "已补假"
                    status_class = "badge-success"
                elif abn.process_remark and "批准" in abn.process_remark:
                    status_text = "已批准"
                    status_class = "badge-success"
            
            abnormal_list.append({
                'id': abn.abnormal_id,
                'name': abn.employee.emp_name,
                'date': abn.abnormal_date.strftime('%Y-%m-%d'),
                'type': ABNORMAL_TYPE_CN.get(abn.abnormal_type.value, abn.abnormal_type.value),
                'duration': duration,
                'remark': abn.abnormal_desc or abn.process_remark or '-',
                'status_text': status_text,
                'status_class': status_class,
                'is_processed': abn.is_processed
            })

        data = {
            'stats': {
                'emp_count': current_emp_count,
                'emp_diff': emp_diff,
                'attendance_rate': attendance_rate,
                'rate_diff': rate_diff,
                'abnormal_count': abnormal_count,
                'abnormal_diff_percent': abnormal_diff_percent,
                'avg_late': avg_late_minutes,
                'late_diff': late_diff
            },
            'charts': {
                'rank': {
                    'names': [x['name'] for x in top_emp_ranks],
                    'rates': [x['rate'] for x in top_emp_ranks]
                },
                'dist': abnormal_pie_data
            },
            'table': abnormal_list
        }
        
        return api_response(200, "获取成功", data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, f"服务器错误: {str(e)}")

@manager_bp.route('/manager/abnormal/list', methods=['GET'])
@api_role_required(['manager'])
def get_abnormal_list():
    """获取异常考勤列表"""
    try:
        current_emp = Employee.query.get(session.get('emp_id'))
        if not current_emp:
            return api_response(401, "未登录或会话过期")
        dept_id = current_emp.dept_id
        
        status = request.args.get('status', 'pending') # pending, processed
        month_str = request.args.get('month', '')
        if not month_str:
            month_str = datetime.now().strftime('%Y-%m')
            
        abnormal_type = request.args.get('type', 'all')
        emp_name = request.args.get('name', '')
        
        query = (
            AbnormalAttendance.query
            .join(AbnormalAttendance.employee)
            .outerjoin(Employee.user)
            .filter(
                Employee.dept_id == dept_id,
                Employee.emp_id != current_emp.emp_id,
                or_(User.role == 'employee', User.user_id.is_(None))
            )
        )
        
        start_date, end_date = get_month_range(month_str)
        query = query.filter(AbnormalAttendance.abnormal_date.between(start_date, end_date))
        
        if status == 'pending':
            query = query.filter(AbnormalAttendance.is_processed == 0)
        else:
            query = query.filter(AbnormalAttendance.is_processed == 1)
            
        if abnormal_type != 'all':
            key = abnormal_type.upper()
            if key in ('MISS', 'MISSING', 'MISSINGCHECK', 'MISSING_CHECK'):
                key = 'MISSING_CHECK'
            try:
                query = query.filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum[key])
            except KeyError:
                pass
            
        if emp_name:
            query = query.filter(Employee.emp_name.like(f'%{emp_name}%'))
            
        records = query.order_by(AbnormalAttendance.abnormal_date.desc()).all()
        
        result = []
        for r in records:
            # Determine status/badge for processed
            status_text = "待处理"
            status_badge = "badge-pending"
            remark_content = r.abnormal_desc or ""
            
            if r.is_processed:
                raw_remark = r.process_remark or ""
                if raw_remark.startswith("[WARN]"):
                    status_text = "已警告"
                    status_badge = "badge-warned"
                    remark_content = raw_remark[6:].strip()
                elif raw_remark.startswith("[MAKEUP]"):
                    status_text = "已补假"
                    status_badge = "badge-makeup"
                    remark_content = raw_remark[8:].strip()
                elif raw_remark.startswith("[APPROVED]"):
                    status_text = "已批准"
                    status_badge = "badge-approved"
                    remark_content = raw_remark[10:].strip()
                elif raw_remark.startswith("[REJECTED]"):
                    status_text = "已驳回"
                    status_badge = "badge-rejected"
                    remark_content = raw_remark[10:].strip()
                else:
                    status_text = "已处理"
                    status_badge = "badge-processed"
                    remark_content = raw_remark

            # Duration calculation
            duration = "-"
            att = Attendance.query.filter_by(emp_id=r.emp_id, att_date=r.abnormal_date).first()
            if r.abnormal_type == AbnormalTypeEnum.LATE and att and att.late_minutes:
                duration = f"{att.late_minutes}分钟"
            elif r.abnormal_type == AbnormalTypeEnum.EARLY and att and att.early_minutes:
                duration = f"{att.early_minutes}分钟"
            
            processor_name = r.processor.emp_name if r.processor else "-"
            process_time = r.update_time.strftime('%Y-%m-%d %H:%M') if r.update_time else "-"

            result.append({
                "id": r.abnormal_id,
                "name": r.employee.emp_name,
                "date": r.abnormal_date.strftime('%Y-%m-%d'),
                "type": ABNORMAL_TYPE_CN.get(r.abnormal_type.value, r.abnormal_type.value),
                "duration": duration,
                "status_text": status_text,
                "status_badge": status_badge,
                "processor": processor_name,
                "process_time": process_time,
                "remark": remark_content
            })
            
        return api_response(200, "success", result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, str(e))

@manager_bp.route('/manager/abnormal/process', methods=['POST'])
@api_role_required(['manager', 'admin'])
def process_abnormal():
    """处理异常考勤"""
    try:
        data = request.json
        abnormal_id = data.get('id')
        action = data.get('action') # approve, reject, warn, makeup, remark (just remark?)
        remark = data.get('remark', '')
        
        abn = AbnormalAttendance.query.get(abnormal_id)
        if not abn:
            return api_response(404, "记录不存在")

        current_emp = Employee.query.get(session.get('emp_id'))
        if not current_emp:
            return api_response(401, "未登录或会话过期")

        role = session.get('role')
        if role == 'manager':
            if abn.employee.dept_id != current_emp.dept_id:
                return api_response(403, "无权处理其他部门记录")
            if int(abn.emp_id) == int(current_emp.emp_id):
                return api_response(403, "经理本人异常需由管理员处理")
            target_user = getattr(abn.employee, 'user', None)
            if target_user and not isinstance(target_user, User) and hasattr(target_user, '__iter__'):
                target_user = next(iter(target_user), None)
            if target_user and getattr(target_user, 'role', None) != 'employee':
                return api_response(403, "经理异常需由管理员处理")
            
        abn.is_processed = 1
        abn.processor_id = current_emp.emp_id
        
        prefix = ""
        if action == 'approve':
            prefix = "[APPROVED] "
        elif action == 'reject':
            prefix = "[REJECTED] "
        elif action == 'warn':
            prefix = "[WARN] "
        elif action == 'makeup':
            prefix = "[MAKEUP] "
            
        abn.process_remark = f"{prefix}{remark}"
        abn.update_time = datetime.now()
        
        db.session.commit()
        return api_response(200, "处理成功")
        
    except Exception as e:
        db.session.rollback()
        return api_response(500, f"处理失败: {str(e)}")

@manager_bp.route('/manager/analysis/data', methods=['GET'])
@api_role_required(['manager'])
def get_analysis_data():
    """获取部门分析数据"""
    try:
        username = session.get('username')
        user = Employee.query.join(Employee.user).filter_by(username=username).first()
        dept_id = user.dept_id
        dept_ids = [dept_id] + get_descendant_dept_ids(dept_id)
        
        # 参数处理
        month_str = request.args.get('month', datetime.now().strftime('%Y-%m'))
        dimension = request.args.get('dimension', 'month') # month, quarter
        indicator = request.args.get('indicator', 'all')
        
        # 计算时间范围
        if dimension == 'month':
            start_date, end_date = get_month_range(month_str)
        elif dimension == 'quarter':
            # 季度处理：优先使用显式参数 year/quarter
            year_arg = request.args.get('year')
            quarter_arg = request.args.get('quarter')
            
            if year_arg and quarter_arg:
                try:
                    y = int(year_arg)
                    q = int(quarter_arg)
                    start_date = date(y, (q - 1) * 3 + 1, 1)
                    if q == 4:
                        end_date = date(y + 1, 1, 1) - timedelta(days=1)
                    else:
                        end_date = date(y, q * 3 + 1, 1) - timedelta(days=1)
                except:
                    # Fallback if params invalid
                    start_date, end_date = get_month_range(month_str)
            else:
                # 兼容旧逻辑或 fallback
                try:
                    y, m = map(int, month_str.split('-'))
                    q = (m - 1) // 3 + 1
                    start_date = date(y, (q - 1) * 3 + 1, 1)
                    if q == 4:
                        end_date = date(y + 1, 1, 1) - timedelta(days=1)
                    else:
                        end_date = date(y, q * 3 + 1, 1) - timedelta(days=1)
                except:
                    start_date, end_date = get_month_range(month_str)

        effective_end_date = min(end_date, date.today())
        if effective_end_date < start_date:
            effective_end_date = end_date
        working_dates = get_working_dates(start_date, effective_end_date) if start_date <= effective_end_date else []

        # 1. 核心指标
        dept_emp_ids = [e.emp_id for e in Employee.query.filter(Employee.dept_id.in_(dept_ids), Employee.status == 1).all()]
        total_emp_count = len(dept_emp_ids)
        days_delta = len(working_dates)
        
        # 公司整体数据（用于对比）
        all_emp_count = Employee.query.filter_by(status=1).count()
        all_person_days = all_emp_count * days_delta
        
        # --- 卡片 1: 出勤率 ---
        total_person_days = total_emp_count * days_delta
        att_count = 0
        if dept_emp_ids and working_dates:
            att_count = Attendance.query.filter(
                Attendance.emp_id.in_(dept_emp_ids),
                Attendance.att_date.in_(working_dates),
                Attendance.is_absent == 0
            ).count()
        att_rate = round((att_count / total_person_days) * 100, 1) if total_person_days > 0 else 0
        
        # 公司平均出勤率
        comp_att_count = 0
        if working_dates:
            comp_att_count = Attendance.query.filter(
                Attendance.att_date.in_(working_dates),
                Attendance.is_absent == 0
            ).count()
        comp_att_rate = round((comp_att_count / all_person_days) * 100, 1) if all_person_days > 0 else 0
        att_diff = round(att_rate - comp_att_rate, 1)

        # --- 卡片 2: 异常率 ---
        abnormal_count = 0
        if dept_emp_ids and working_dates:
            abnormal_count = AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id.in_(dept_emp_ids),
                AbnormalAttendance.abnormal_date.in_(working_dates)
            ).count()
        abnormal_rate = round((abnormal_count / total_person_days) * 100, 1) if total_person_days > 0 else 0
        
        # 公司平均异常率
        comp_abnormal_count = 0
        if working_dates:
            comp_abnormal_count = AbnormalAttendance.query.filter(
                AbnormalAttendance.abnormal_date.in_(working_dates)
            ).count()
        comp_abnormal_rate = round((comp_abnormal_count / all_person_days) * 100, 1) if all_person_days > 0 else 0
        abnormal_diff = round(abnormal_rate - comp_abnormal_rate, 1)
        
        # --- 卡片 3: 平均打卡时长 ---
        total_work_minutes = 0
        if dept_emp_ids and working_dates:
            total_work_minutes = db.session.query(func.sum(Attendance.work_duration)).filter(
                Attendance.emp_id.in_(dept_emp_ids),
                Attendance.att_date.in_(working_dates)
            ).scalar() or 0
        avg_work_hours = round((total_work_minutes / att_count) / 60, 1) if att_count > 0 else 0
        
        # 公司平均时长
        comp_work_minutes = 0
        if working_dates:
            comp_work_minutes = db.session.query(func.sum(Attendance.work_duration)).filter(
                Attendance.att_date.in_(working_dates)
            ).scalar() or 0
        comp_avg_work_hours = round((comp_work_minutes / comp_att_count) / 60, 1) if comp_att_count > 0 else 0
        work_diff = round(avg_work_hours - comp_avg_work_hours, 1)
        
        # --- 卡片 4: 旷工率 ---
        absent_count = 0
        if dept_emp_ids and working_dates:
            absent_count = Attendance.query.filter(
                Attendance.emp_id.in_(dept_emp_ids),
                Attendance.att_date.in_(working_dates),
                Attendance.is_absent == 1
            ).count()
        absent_rate = round((absent_count / total_person_days) * 100, 1) if total_person_days > 0 else 0
        
        # 公司平均旷工率
        comp_absent_count = 0
        if working_dates:
            comp_absent_count = Attendance.query.filter(
                Attendance.att_date.in_(working_dates),
                Attendance.is_absent == 1
            ).count()
        comp_absent_rate = round((comp_absent_count / all_person_days) * 100, 1) if all_person_days > 0 else 0
        absent_diff = round(absent_rate - comp_absent_rate, 1)
        
        
        # 2. Charts Data (Affected by Dimension/Indicator)
        
        # Trend Chart (Week/Day/Month)
        trend_label = []
        trend_data = []
        
        if dimension == 'month':
             # Weekly trend within the month
             curr = start_date
             trend_end = effective_end_date
             idx = 1
             while curr <= trend_end:
                next_week = curr + timedelta(days=7)
                week_end = min(next_week - timedelta(days=1), trend_end)
                w_working_dates = get_working_dates(curr, week_end) if curr <= week_end else []
                w_person_days = total_emp_count * len(w_working_dates)
                
                # Logic based on Indicator
                val = 0
                if indicator == 'abnormal':
                    cnt = 0
                    if dept_emp_ids and w_working_dates:
                        cnt = AbnormalAttendance.query.filter(
                            AbnormalAttendance.emp_id.in_(dept_emp_ids),
                            AbnormalAttendance.abnormal_date.in_(w_working_dates)
                        ).count()
                    val = round((cnt / w_person_days) * 100, 1) if w_person_days > 0 else 0
                elif indicator == 'check-time':
                    # Avg hours
                    w_mins = 0
                    w_att_cnt = 0
                    if dept_emp_ids and w_working_dates:
                        w_mins = db.session.query(func.sum(Attendance.work_duration)).filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(w_working_dates)
                        ).scalar() or 0
                        w_att_cnt = Attendance.query.filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(w_working_dates),
                            Attendance.is_absent == 0
                        ).count()
                    val = round((w_mins / w_att_cnt) / 60, 1) if w_att_cnt > 0 else 0
                else: # Default: attendance rate
                    cnt = 0
                    if dept_emp_ids and w_working_dates:
                        cnt = Attendance.query.filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(w_working_dates),
                            Attendance.is_absent == 0
                        ).count()
                    val = round((cnt / w_person_days) * 100, 1) if w_person_days > 0 else 0
                
                trend_data.append(val)
                trend_label.append(f"{curr.strftime('%m.%d')}-{week_end.strftime('%m.%d')}")
                curr = next_week
                idx += 1
                
        elif dimension == 'quarter':
             # Monthly trend within quarter
             curr = start_date
             trend_end = effective_end_date
             while curr <= trend_end:
                 m_next = (curr.replace(day=1) + timedelta(days=32)).replace(day=1)
                 m_end = m_next - timedelta(days=1)
                 if m_end > trend_end: m_end = trend_end
                 
                 m_working_dates = get_working_dates(curr, m_end) if curr <= m_end else []
                 m_person_days = total_emp_count * len(m_working_dates)
                 
                 val = 0
                 # ... (Similar logic for indicator, abbreviated for brevity, using attendance default for now or copy logic)
                 if indicator == 'abnormal':
                    cnt = 0
                    if dept_emp_ids and m_working_dates:
                        cnt = AbnormalAttendance.query.filter(
                            AbnormalAttendance.emp_id.in_(dept_emp_ids),
                            AbnormalAttendance.abnormal_date.in_(m_working_dates)
                        ).count()
                    val = round((cnt / m_person_days) * 100, 1) if m_person_days > 0 else 0
                 elif indicator == 'check-time':
                    m_mins = 0
                    m_att_cnt = 0
                    if dept_emp_ids and m_working_dates:
                        m_mins = db.session.query(func.sum(Attendance.work_duration)).filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(m_working_dates),
                            Attendance.is_absent == 0
                        ).scalar() or 0
                        m_att_cnt = Attendance.query.filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(m_working_dates),
                            Attendance.is_absent == 0
                        ).count()
                    val = round((m_mins / m_att_cnt) / 60, 1) if m_att_cnt > 0 else 0
                 else:
                    cnt = 0
                    if dept_emp_ids and m_working_dates:
                        cnt = Attendance.query.filter(
                            Attendance.emp_id.in_(dept_emp_ids),
                            Attendance.att_date.in_(m_working_dates),
                            Attendance.is_absent == 0
                        ).count()
                    val = round((cnt / m_person_days) * 100, 1) if m_person_days > 0 else 0

                 trend_data.append(val)
                 trend_label.append(curr.strftime('%m月'))
                 curr = m_next
        
        # Dept vs Company (Monthly Trend for the Year - Keep as is or adjust?)
        # Let's keep the existing "Compare" chart as a 6-month view regardless of selection, 
        # OR make it follow the dimension. Let's keep it 6-month for broader context.
        # ... (Previous code for Compare Chart) ...
        # Copied from previous implementation for continuity
        trend_months = []
        trend_dept_comp = []
        trend_comp_comp = []
        
        # Determine loop range based on dimension
        loop_range = []
        if dimension == 'quarter':
            # 季度模式：展示该季度的 3 个月
            # start_date 已经是该季度第一天
            for i in range(3):
                # i = 0, 1, 2
                # Calculate month based on start_date
                # Need to handle year wrap if any (though quarter start is usually year-aligned except Q4?)
                # Q1: 1,2,3; Q2: 4,5,6...
                # Simple logic: start_date + i months
                y = start_date.year
                m = start_date.month + i
                if m > 12:
                    m -= 12
                    y += 1
                loop_range.append((y, m))
        else:
            # 月度模式：展示所选月份所在年份的 1月 - 12月
            # 这样能直观展示当年的完整趋势，避免跨年显示的困惑
            target_year = start_date.year
            for m in range(1, 13):
                loop_range.append((target_year, m))
        
        for y, m in loop_range:
             m_start = date(y, m, 1)
             if m == 12:
                 m_end = date(y+1, 1, 1) - timedelta(days=1)
             else:
                 m_end = date(y, m+1, 1) - timedelta(days=1)
             
             trend_months.append(f"{m}月")
             
             if m_start > date.today():
                 trend_dept_comp.append(None)
                 trend_comp_comp.append(None)
                 continue

             m_end_limit = m_end
             if m_start.year == date.today().year and m_start.month == date.today().month:
                 m_end_limit = min(m_end, date.today())

             m_working_dates = get_working_dates(m_start, m_end_limit) if m_start <= m_end_limit else []

             # Dept
             d_p_days = total_emp_count * len(m_working_dates)
             d_att = 0
             if dept_emp_ids and m_working_dates:
                 d_att = Attendance.query.filter(
                    Attendance.emp_id.in_(dept_emp_ids),
                    Attendance.att_date.in_(m_working_dates),
                    Attendance.is_absent == 0
                 ).count()
             
             # 如果该月没有任何数据（d_p_days > 0 但 d_att = 0），我们还需要检查是否是未来月份
             # 如果当前月份 < m_start，那么该月还没有发生，出勤率应为 0 或者不显示（这里置为0）
             # 实际上，如果 d_att 为 0，出勤率就是 0。
             # 但问题在于 d_p_days 是基于员工总数 * 天数计算的，即便没有打卡记录，分母也不为0。
             # 所以如果分子为0，结果就是0%。
             # 可是用户反馈"明明没有数据，还显示比平均高"。
             # 如果公司平均也是0，那么 dept=0, comp=0，持平。
             # 如果公司平均 > 0 (比如有人误操作录入了未来数据？或者逻辑有误)，就会出现差异。
             # 另一种可能是：在计算趋势时，如果该月还没有到，应该返回 null 或者 0，前端不显示？
             # 但 ECharts 如果数据是 0 会显示在底部。
             # 让我们检查一下逻辑：
             # 如果 m_start > date.today()，那么该月是未来月份，应该设为 None 或 0
             
             trend_dept_comp.append(round((d_att / d_p_days) * 100, 1) if d_p_days > 0 else 0)
             
             # Company
             c_p_days = all_emp_count * len(m_working_dates)
             c_att = 0
             if m_working_dates:
                 c_att = Attendance.query.filter(
                    Attendance.att_date.in_(m_working_dates),
                    Attendance.is_absent == 0
                 ).count()
             trend_comp_comp.append(round((c_att / c_p_days) * 100, 1) if c_p_days > 0 else 0)

        # Emp Abnormal Rank
        # ... (Previous code)
        emp_ranks = []
        for eid in dept_emp_ids:
            emp = Employee.query.get(eid)
            cnt = 0
            if working_dates:
                cnt = AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id == eid,
                    AbnormalAttendance.abnormal_date.in_(working_dates)
                ).count()
            if cnt > 0:
                emp_ranks.append({'name': emp.emp_name, 'count': cnt})
        emp_ranks.sort(key=lambda x: x['count'], reverse=True)
        top_emp_ranks = emp_ranks[:6]

        # 3. Sub-groups Table
        # ... (Previous code)
        sub_depts = Department.query.filter_by(parent_dept_id=dept_id, status=1).all()
        table_data = []
        if sub_depts:
            for sd in sub_depts:
                sd_emps = [e.emp_id for e in sd.employees if e.status == 1]
                sd_count = len(sd_emps)
                sd_p_days = sd_count * days_delta
                
                # Real stats for subgroup
                sd_att = 0
                if sd_emps and working_dates:
                    sd_att = Attendance.query.filter(
                        Attendance.emp_id.in_(sd_emps),
                        Attendance.att_date.in_(working_dates),
                        Attendance.is_absent == 0
                    ).count()
                sd_rate = round((sd_att / sd_p_days) * 100, 1) if sd_p_days > 0 else 0
                
                sd_abn = 0
                if sd_emps and working_dates:
                    sd_abn = AbnormalAttendance.query.filter(
                        AbnormalAttendance.emp_id.in_(sd_emps),
                        AbnormalAttendance.abnormal_date.in_(working_dates)
                    ).count()
                
                sd_late_mins = 0
                sd_late_cnt = 0
                if sd_emps and working_dates:
                    sd_late_mins = db.session.query(func.sum(Attendance.late_minutes)).filter(
                        Attendance.emp_id.in_(sd_emps),
                        Attendance.att_date.in_(working_dates)
                    ).scalar() or 0
                    sd_late_cnt = Attendance.query.filter(
                        Attendance.emp_id.in_(sd_emps),
                        Attendance.att_date.in_(working_dates),
                        Attendance.late_minutes > 0
                    ).count()
                sd_avg_late = int(sd_late_mins / sd_late_cnt) if sd_late_cnt > 0 else 0
                
                sd_absent = 0
                if sd_emps and working_dates:
                    sd_absent = Attendance.query.filter(
                        Attendance.emp_id.in_(sd_emps),
                        Attendance.att_date.in_(working_dates),
                        Attendance.is_absent == 1
                    ).count()

                table_data.append({
                    "name": sd.dept_name,
                    "emp_count": sd_count,
                    "att_rate": f"{sd_rate}%",
                    "abnormal_count": sd_abn,
                    "avg_late": f"{sd_avg_late}分钟",
                    "absent_count": sd_absent
                })

        data = {
            "cards": {
                "att_rate": att_rate,
                "att_diff": att_diff,
                "abnormal_rate": abnormal_rate,
                "abnormal_diff": abnormal_diff,
                "avg_work_hours": avg_work_hours,
                "work_diff": work_diff,
                "absent_rate": absent_rate,
                "absent_diff": absent_diff
            },
            "charts": {
                "week_trend": {"labels": trend_label, "data": trend_data},
                "compare": {"labels": trend_months, "dept": trend_dept_comp, "comp": trend_comp_comp},
                "rank": {"names": [x['name'] for x in top_emp_ranks], "counts": [x['count'] for x in top_emp_ranks]}
            },
            "table": table_data
        }
        
        return api_response(200, "success", data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, str(e))
