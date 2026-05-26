# api/dashboard_api.py
from typing import Dict, List, Any, Tuple, Optional
from datetime import date, datetime, timedelta

from flask import request, jsonify
from sqlalchemy import and_, or_, func

from models import db, Employee, Attendance, AbnormalAttendance, Department, AbnormalTypeEnum, SystemConfig
from utils.cache_utils import cached

from utils.api_helpers import api_response, get_month_range, ABNORMAL_TYPE_CN, get_working_days
from utils.decorators import api_role_required

def get_warning_list(start_date, end_date, sys_config):
    """根据配置获取本月考勤预警列表（迟到/旷工超标）"""
    try:
        late_max = int(float(sys_config.get('lateMaxCount', 3)))
        absent_max = int(float(sys_config.get('absentMaxCount', 1)))
        
        # 统计本月每个人的迟到和旷工次数
        warnings = []
        
        # 迟到统计
        late_stats = db.session.query(
            Attendance.emp_id, 
            Employee.emp_name,
            Department.dept_name,
            func.count(Attendance.att_id).label('count')
        ).join(Employee, Attendance.emp_id == Employee.emp_id) \
         .join(Department, Employee.dept_id == Department.dept_id) \
         .filter(Attendance.att_date.between(start_date, end_date), Attendance.late_minutes > 0) \
         .group_by(Attendance.emp_id).having(func.count(Attendance.att_id) >= late_max).all()
        
        for s in late_stats:
            warnings.append({
                "emp_id": s.emp_id,
                "emp_name": s.emp_name,
                "dept_name": s.dept_name,
                "type": "迟到超标",
                "count": s.count,
                "limit": late_max,
                "level": "warning"
            })
            
        # 旷工统计
        absent_stats = db.session.query(
            Attendance.emp_id, 
            Employee.emp_name,
            Department.dept_name,
            func.count(Attendance.att_id).label('count')
        ).join(Employee, Attendance.emp_id == Employee.emp_id) \
         .join(Department, Employee.dept_id == Department.dept_id) \
         .filter(Attendance.att_date.between(start_date, end_date), Attendance.is_absent == 1) \
         .group_by(Attendance.emp_id).having(func.count(Attendance.att_id) >= absent_max).all()
        
        for s in absent_stats:
            warnings.append({
                "emp_id": s.emp_id,
                "emp_name": s.emp_name,
                "dept_name": s.dept_name,
                "type": "旷工预警",
                "count": s.count,
                "limit": absent_max,
                "level": "danger"
            })
            
        return warnings
    except Exception:
        return []

# 函数定义保持不变
@cached(timeout=300, key_prefix='dashboard')
def get_dashboard_data() -> Any:
    # 获取请求参数（支持按月 month=YYYY-MM 或按年 year=YYYY）
    month = request.args.get('month')
    year = request.args.get('year')
    quarter = request.args.get('quarter')  # expected values: 'Q1','Q2','Q3','Q4'
    current_date = date.today()

    # 解析时间范围
    try:
        if quarter and year:
            y = int(year)
            q = quarter.upper()
            if q == 'Q1':
                start_date = date(y, 1, 1)
                end_date = date(y, 3, 31)
            elif q == 'Q2':
                start_date = date(y, 4, 1)
                end_date = date(y, 6, 30)
            elif q == 'Q3':
                start_date = date(y, 7, 1)
                end_date = date(y, 9, 30)
            elif q == 'Q4':
                start_date = date(y, 10, 1)
                end_date = date(y, 12, 31)
            else:
                return api_response(400, f"季度格式错误：{quarter}")
            mode = 'quarter'
        elif year:
            y = int(year)
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
            mode = 'year'
        else:
            # default: month param or current month
            month = month or datetime.now().strftime('%Y-%m')
            start_date, end_date = get_month_range(month)
            mode = 'month'
    except Exception as e:
        return api_response(400, f"日期格式错误：{str(e)}")

    sys_config = {}
    try:
        sys_config = {c.config_key: c.config_value for c in SystemConfig.query.all()}
    except Exception:
        sys_config = {}

    try:
        late_threshold = int(float(sys_config.get('lateThreshold') or 0))
    except Exception:
        late_threshold = 0

    try:
        early_threshold = int(float(sys_config.get('earlyLeaveThreshold') or 0))
    except Exception:
        early_threshold = 0

    # 1. 总员工数（在职）
    total_emp_count = Employee.query.filter_by(status=1).count()

    # 2. 本月出勤率
    active_emps = Employee.query.filter_by(status=1).all()
    active_emp_ids = [emp.emp_id for emp in active_emps]
    active_emp_count = len(active_emp_ids)
    month_days = get_working_days(start_date, end_date)

    monthly_attendance_rate = 0.0
    if active_emp_count > 0 and month_days > 0:
        attendance_count = Attendance.query.filter(
            Attendance.emp_id.in_(active_emp_ids),
            Attendance.att_date.between(start_date, end_date),
            Attendance.is_absent == 0
        ).count()
        monthly_attendance_rate = round(attendance_count / (active_emp_count * month_days) * 100, 1)

    abnormal_cond = or_(
        and_(
            AbnormalAttendance.abnormal_type == AbnormalTypeEnum.LATE,
            or_(Attendance.late_minutes.is_(None), Attendance.late_minutes > late_threshold),
        ),
        and_(
            AbnormalAttendance.abnormal_type == AbnormalTypeEnum.EARLY,
            or_(Attendance.early_minutes.is_(None), Attendance.early_minutes > early_threshold),
        ),
        AbnormalAttendance.abnormal_type.notin_([AbnormalTypeEnum.LATE, AbnormalTypeEnum.EARLY]),
    )

    # 4. 旷工人数（去重）
    absent_emp_count = 0
    if active_emp_ids:
        absent_result = Attendance.query.filter(
            Attendance.emp_id.in_(active_emp_ids),
            Attendance.att_date.between(start_date, end_date),
            Attendance.is_absent == 1
        ).with_entities(Attendance.emp_id).distinct().all()
        absent_emp_count = len({row[0] for row in absent_result})

    # 5. 月度出勤率趋势
    trend_data = []
    
    def get_aggregated_attendance(start_d, end_d, active_ids):
        if not active_ids:
            return {}
        
        # 使用聚合查询一次性获取指定范围内各月的分组统计
        results = db.session.query(
            func.date_format(Attendance.att_date, '%Y-%m').label('month'),
            func.count(Attendance.att_id).label('count')
        ).filter(
            Attendance.emp_id.in_(active_ids),
            Attendance.att_date.between(start_d, end_d),
            Attendance.is_absent == 0
        ).group_by('month').all()
        
        return {r.month: r.count for r in results}

    if mode == 'year':
        selected_year = start_date.year
        # 获取整年数据（一次查询）
        year_att_data = get_aggregated_attendance(date(selected_year, 1, 1), date(selected_year, 12, 31), active_emp_ids)
        
        for m in range(1, 13):
            calc_month_str = f"{selected_year}-{m:02d}"
            calc_start = date(selected_year, m, 1)
            next_month = date(selected_year + 1, 1, 1) if m == 12 else date(selected_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                att_count = year_att_data.get(calc_month_str, 0)
                rate = round(att_count / (active_emp_count * calc_month_days) * 100, 1)
            trend_data.append(rate)
            
        # 年度平均出勤率（仅计算已过且有数据的月份平均值，避免被未来月份的0值拉低）
        if start_date.year == current_date.year:
            valid_months_data = [r for i, r in enumerate(trend_data) if i < current_date.month and r > 0]
        else:
            valid_months_data = [r for r in trend_data if r > 0]
        monthly_attendance_rate = round(sum(valid_months_data) / len(valid_months_data), 1) if valid_months_data else 0.0

    elif mode == 'quarter':
        selected_year = start_date.year
        # 获取整年数据（用于趋势图展示）
        year_att_data = get_aggregated_attendance(date(selected_year, 1, 1), date(selected_year, 12, 31), active_emp_ids)
        
        for m in range(1, 13):
            calc_month_str = f"{selected_year}-{m:02d}"
            calc_start = date(selected_year, m, 1)
            next_month = date(selected_year + 1, 1, 1) if m == 12 else date(selected_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                att_count = year_att_data.get(calc_month_str, 0)
                rate = round(att_count / (active_emp_count * calc_month_days) * 100, 1)
            trend_data.append(rate)
            
        # 季度平均出勤率（只统计季度的月份）
        q_months = []
        cur = start_date
        while cur <= end_date:
            if cur.month not in q_months:
                q_months.append(cur.month)
            cur += timedelta(days=1)
        quarter_rates = [trend_data[m-1] for m in q_months]
        monthly_attendance_rate = round(sum(quarter_rates) / len(quarter_rates), 1) if quarter_rates else 0.0
    else:
        # month-based: 获取过去12个月数据
        current_year, current_month = map(int, month.split('-'))
        # 计算12个月前的起始日期
        trend_start_year = current_year
        trend_start_month = current_month - 11
        if trend_start_month <= 0:
            trend_start_month += 12
            trend_start_year -= 1
        trend_start_date = date(trend_start_year, trend_start_month, 1)
        
        # 一次查询获取过去12个月数据
        past_att_data = get_aggregated_attendance(trend_start_date, end_date, active_emp_ids)
        
        for i in range(11, -1, -1):
            calc_month = current_month - i
            calc_year = current_year
            if calc_month <= 0:
                calc_month += 12
                calc_year -= 1
            calc_month_str = f"{calc_year}-{calc_month:02d}"
            calc_start, calc_end = get_month_range(calc_month_str)
            calc_month_days = get_working_days(calc_start, calc_end)

            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                att_count = past_att_data.get(calc_month_str, 0)
                rate = round(att_count / (active_emp_count * calc_month_days) * 100, 1)
            trend_data.append(rate)

    # 6. 部门异常分布优化
    dept_abnormal_data = []
    if active_emp_ids:
        # 一次性获取所有部门的异常统计
        dept_results = db.session.query(
            Department.dept_name,
            func.count(AbnormalAttendance.abnormal_id).label('count')
        ).join(Employee, Employee.dept_id == Department.dept_id) \
         .join(AbnormalAttendance, AbnormalAttendance.emp_id == Employee.emp_id) \
         .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date)) \
         .filter(
            Department.status == 1,
            Employee.status == 1,
            AbnormalAttendance.abnormal_date.between(start_date, end_date),
            abnormal_cond
         ).group_by(Department.dept_id).all()
        
        dept_counts = {r.dept_name: r.count for r in dept_results}
        
        # 补充没有异常记录的部门
        all_depts = Department.query.filter_by(status=1).all()
        for dept in all_depts:
            dept_abnormal_data.append({
                "name": dept.dept_name,
                "value": dept_counts.get(dept.dept_name, 0)
            })
    else:
        all_depts = Department.query.filter_by(status=1).all()
        for dept in all_depts:
            dept_abnormal_data.append({"name": dept.dept_name, "value": 0})

    raw_abnormal_records = []
    if active_emp_ids:
        raw_abnormal_records = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id.in_(active_emp_ids),
                AbnormalAttendance.abnormal_date.between(start_date, end_date),
            )
            .join(Employee, AbnormalAttendance.emp_id == Employee.emp_id)
            .join(Department, Employee.dept_id == Department.dept_id)
            .outerjoin(
                Attendance,
                (AbnormalAttendance.emp_id == Attendance.emp_id)
                & (AbnormalAttendance.abnormal_date == Attendance.att_date),
            )
            .filter(abnormal_cond)
            .with_entities(
                AbnormalAttendance.abnormal_id,
                AbnormalAttendance.emp_id,
                Employee.emp_name,
                Department.dept_name,
                AbnormalAttendance.abnormal_date,
                AbnormalAttendance.abnormal_type,
                db.case(
                    (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.LATE, Attendance.late_minutes),
                    (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.EARLY, Attendance.early_minutes),
                    else_=None,
                ).label("abnormal_duration"),
                AbnormalAttendance.is_processed,
                AbnormalAttendance.create_time,
                AbnormalAttendance.abnormal_desc,
                AbnormalAttendance.process_remark,
            )
            .order_by(AbnormalAttendance.abnormal_date.desc())
            .all()
        )

    filtered_abnormal_records = raw_abnormal_records

    # 8. 异常类型分布 (需重新统计，因为过滤了部分记录)
    abnormal_type_counts = {
        AbnormalTypeEnum.LATE: 0,
        AbnormalTypeEnum.EARLY: 0,
        AbnormalTypeEnum.ABSENT: 0,
        AbnormalTypeEnum.MISSING_CHECK: 0
    }
    
    # 重新统计过滤后的类型数量
    for rec in filtered_abnormal_records:
        abn_type = rec[3]
        if abn_type in abnormal_type_counts:
            abnormal_type_counts[abn_type] += 1
            
    abnormal_type_data = []
    for abn_type, count in abnormal_type_counts.items():
        type_name = ABNORMAL_TYPE_CN.get(abn_type.value, abn_type.value)
        abnormal_type_data.append({
            "name": type_name,
            "value": count
        })

    # 更新 monthly_abnormal_count 为过滤后的总数
    monthly_abnormal_count = len(filtered_abnormal_records)

    formatted_records = []
    for rec in filtered_abnormal_records:
        abnormal_id, emp_id, emp_name, dept_name, abn_date, abn_type, duration, is_processed, create_time, abnormal_desc, raw_remark = rec
        
        status_text = "待处理"
        status_class = "badge-warning"
        display_remark = abnormal_desc or ""
        
        if is_processed:
            status_text = "已处理"
            status_class = "badge-success"
            remark_val = raw_remark or ""
            
            if remark_val.startswith("[WARN]"):
                status_text = "已警告"
                status_class = "badge-warned"
                display_remark = remark_val[6:].strip()
            elif remark_val.startswith("[MAKEUP]"):
                status_text = "已补假"
                status_class = "badge-makeup"
                display_remark = remark_val[8:].strip()
            elif remark_val.startswith("[APPROVED]"):
                status_text = "已批准"
                status_class = "badge-approved"
                display_remark = remark_val[10:].strip()
            elif remark_val.startswith("[REJECTED]"):
                status_text = "已驳回"
                status_class = "badge-rejected"
                display_remark = remark_val[10:].strip()
            else:
                display_remark = remark_val or (abnormal_desc or "")

        formatted_records.append({
            "abnormal_id": abnormal_id,
            "emp_id": emp_id,
            "employee_name": emp_name,
            "department_name": dept_name,
            "abnormal_date": abn_date.strftime('%Y-%m-%d'),
            "abnormal_type": abn_type.value, # Return the enum value for frontend mapping if needed
            "abnormal_duration": duration if duration else "",
            "status": status_text,
            "status_class": status_class,
            "remark": display_remark,
            "create_time": create_time.strftime('%Y-%m-%d %H:%M:%S') if create_time else ""
        })

    # ========== 計算與去年/上期的對比數據 ==========
    employee_growth_rate = 0.0
    attendance_growth_rate = 0.0
    abnormal_drop_rate = 0.0
    absent_drop_rate = 0.0

    if mode == 'year':
        # 按年模式：與去年同期對比（使用相同的月份範圍）
        prev_year = start_date.year - 1

        # 確定當前年已經過了哪些月份（使用當前日期來限制比較範圍）
        # 如果是當前年，則只比較到當前月份；否則比較全年
        if start_date.year == current_date.year:
            # 比較從1月到當前月份的數據
            compare_end_month = current_date.month
            compare_end_date = current_date
            prev_compare_end_date = date(prev_year, current_date.month, current_date.day)
        else:
            # 比較全年12個月
            compare_end_month = 12
            compare_end_date = end_date
            prev_compare_end_date = date(prev_year, 12, 31)

        # 構建當前年和去年的比較時間範圍
        compare_months = range(1, compare_end_month + 1)

        # 一次性获取当前年和去年的聚合出勤统计（合并查询优化）
        current_year_data = get_aggregated_attendance(date(start_date.year, 1, 1), end_date, active_emp_ids)
        prev_year_data = get_aggregated_attendance(date(prev_year, 1, 1), prev_compare_end_date, active_emp_ids)

        # 計算當年已過月份的出勤率（年度平均）
        current_attendance_rates = []
        for m in compare_months:
            calc_month_str = f"{start_date.year}-{m:02d}"
            calc_start = date(start_date.year, m, 1)
            next_month = date(start_date.year + 1, 1, 1) if m == 12 else date(start_date.year, m + 1, 1)
            calc_end = min(next_month - timedelta(days=1), end_date)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                att_count = current_year_data.get(calc_month_str, 0)
                rate = round(att_count / (active_emp_count * calc_month_days) * 100, 1)
            current_attendance_rates.append(rate)
            
        # 仅统计有数据的月份平均值，避免被未开始或无数据的月份拉低
        valid_current_rates = [r for r in current_attendance_rates if r > 0]
        current_avg_attendance = round(sum(valid_current_rates) / len(valid_current_rates), 1) if valid_current_rates else 0.0

        # 計算去年同期的出勤率
        prev_attendance_rates = []
        for m in compare_months:
            calc_month_str = f"{prev_year}-{m:02d}"
            calc_start = date(prev_year, m, 1)
            next_month = date(prev_year + 1, 1, 1) if m == 12 else date(prev_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                att_count = prev_year_data.get(calc_month_str, 0)
                rate = round(att_count / (active_emp_count * calc_month_days) * 100, 1)
            prev_attendance_rates.append(rate)
        
        # 仅统计去年同期有数据的月份平均值，确保对比公平
        valid_prev_rates = [r for r in prev_attendance_rates if r > 0]
        prev_avg_attendance = round(sum(valid_prev_rates) / len(valid_prev_rates), 1) if valid_prev_rates else 0.0

        def count_abnormal(start_d: date, end_d: date) -> int:
            if not active_emp_ids:
                return 0
            return (
                AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id.in_(active_emp_ids),
                    AbnormalAttendance.abnormal_date.between(start_d, end_d),
                )
                .outerjoin(
                    Attendance,
                    (AbnormalAttendance.emp_id == Attendance.emp_id)
                    & (AbnormalAttendance.abnormal_date == Attendance.att_date),
                )
                .filter(abnormal_cond)
                .count()
            )

        current_abnormal_count = count_abnormal(start_date, compare_end_date)
        prev_abnormal_count = count_abnormal(date(prev_year, 1, 1), prev_compare_end_date)

        # 計算當年和去年同期的曠工人數
        current_absent_emp_ids_set = set()
        prev_absent_emp_ids_set = set()
        
        current_absent_result = Attendance.query.filter(
            Attendance.emp_id.in_(active_emp_ids),
            Attendance.att_date.between(start_date, compare_end_date),
            Attendance.is_absent == 1
        ).with_entities(Attendance.emp_id).distinct().all()
        for row in current_absent_result:
            current_absent_emp_ids_set.add(row[0])

        prev_absent_result = Attendance.query.filter(
            Attendance.emp_id.in_(active_emp_ids),
            Attendance.att_date.between(date(prev_year, 1, 1), prev_compare_end_date),
            Attendance.is_absent == 1
        ).with_entities(Attendance.emp_id).distinct().all()
        for row in prev_absent_result:
            prev_absent_emp_ids_set.add(row[0])
            
        current_absent_emp_count = len(current_absent_emp_ids_set)
        prev_absent_emp_count = len(prev_absent_emp_ids_set)

        # 計算增長/下降率
        if prev_avg_attendance > 0:
            attendance_growth_rate = round((current_avg_attendance - prev_avg_attendance) / prev_avg_attendance * 100, 1)
        else:
            attendance_growth_rate = 0.0

        # 异常次数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_abnormal_count > 0:
            abnormal_drop_rate = round((prev_abnormal_count - current_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_drop_rate = 0.0

        # 旷工人数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_absent_emp_count > 0:
            absent_drop_rate = round((prev_absent_emp_count - current_absent_emp_count) / prev_absent_emp_count * 100, 1)
        else:
            absent_drop_rate = 0.0

        # 员工增长率：无历史快照数据，暂不计算
        employee_growth_rate = 0.0

        # 更新 monthly_attendance_rate 為當年已過月份的平均值
        monthly_attendance_rate = current_avg_attendance
        # 更新 absent_emp_count 為當年已過月份的總曠工人數
        absent_emp_count = current_absent_emp_count

    elif mode == 'quarter':
        # 按季度模式：與上季度對比
        q = quarter.upper()
        current_quarter_months = []
        cur = start_date
        while cur <= end_date:
            if cur.month not in current_quarter_months:
                current_quarter_months.append(cur.month)
            cur += timedelta(days=1)

        # 計算上季度的時間範圍
        if q == 'Q1':
            prev_quarter_months = [10, 11, 12]
            prev_year = start_date.year - 1
        elif q == 'Q2':
            prev_quarter_months = [1, 2, 3]
            prev_year = start_date.year
        elif q == 'Q3':
            prev_quarter_months = [4, 5, 6]
            prev_year = start_date.year
        elif q == 'Q4':
            prev_quarter_months = [7, 8, 9]
            prev_year = start_date.year

        # 計算上季度的數據
        prev_start_month = prev_quarter_months[0]
        prev_start = date(prev_year, prev_start_month, 1)
        prev_end_month = prev_quarter_months[-1]
        next_month = date(prev_year + 1, 1, 1) if prev_end_month == 12 else date(prev_year, prev_end_month + 1, 1)
        prev_end = next_month - timedelta(days=1)

        # 上季度出勤率
        prev_quarter_rates = []
        for m in prev_quarter_months:
            calc_start = date(prev_year, m, 1)
            next_m = date(prev_year + 1, 1, 1) if m == 12 else date(prev_year, m + 1, 1)
            calc_end = next_m - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if active_emp_count > 0 and calc_month_days > 0:
                calc_att_count = Attendance.query.filter(
                    Attendance.emp_id.in_(active_emp_ids),
                    Attendance.att_date.between(calc_start, calc_end),
                    Attendance.is_absent == 0
                ).count()
                rate = round(calc_att_count / (active_emp_count * calc_month_days) * 100, 1)
            prev_quarter_rates.append(rate)
        prev_quarter_avg_attendance = round(sum(prev_quarter_rates) / len(prev_quarter_rates), 1) if prev_quarter_rates else 0.0

        prev_abnormal_count = 0
        if active_emp_ids:
            prev_abnormal_count = (
                AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id.in_(active_emp_ids),
                    AbnormalAttendance.abnormal_date.between(prev_start, prev_end),
                )
                .outerjoin(
                    Attendance,
                    (AbnormalAttendance.emp_id == Attendance.emp_id)
                    & (AbnormalAttendance.abnormal_date == Attendance.att_date),
                )
                .filter(abnormal_cond)
                .count()
            )

        current_abnormal_count = 0
        if active_emp_ids:
            current_abnormal_count = (
                AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id.in_(active_emp_ids),
                    AbnormalAttendance.abnormal_date.between(date(start_date.year, current_quarter_months[0], 1), end_date),
                )
                .outerjoin(
                    Attendance,
                    (AbnormalAttendance.emp_id == Attendance.emp_id)
                    & (AbnormalAttendance.abnormal_date == Attendance.att_date),
                )
                .filter(abnormal_cond)
                .count()
            )
            
        current_absent_emp_count = 0
        if active_emp_ids:
            current_absent_result = Attendance.query.filter(
                Attendance.emp_id.in_(active_emp_ids),
                Attendance.att_date.between(date(start_date.year, current_quarter_months[0], 1), end_date),
                Attendance.is_absent == 1
            ).with_entities(Attendance.emp_id).distinct().all()
            current_absent_emp_count = len({row[0] for row in current_absent_result})

        # 上季度旷工人数（去重）
        prev_absent_emp_count = 0
        if active_emp_ids:
            prev_absent_result = Attendance.query.filter(
                Attendance.emp_id.in_(active_emp_ids),
                Attendance.att_date.between(prev_start, prev_end),
                Attendance.is_absent == 1
            ).with_entities(Attendance.emp_id).distinct().all()
            prev_absent_emp_count = len({row[0] for row in prev_absent_result})

        # 計算增長/下降率
        current_quarter_attendance = monthly_attendance_rate  # 季度平均出勤率
        if prev_quarter_avg_attendance > 0:
            attendance_growth_rate = round((current_quarter_attendance - prev_quarter_avg_attendance) / prev_quarter_avg_attendance * 100, 1)
        else:
            attendance_growth_rate = 0.0

        # 异常次数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_abnormal_count > 0:
            abnormal_drop_rate = round((prev_abnormal_count - current_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_drop_rate = 0.0

        # 旷工人数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_absent_emp_count > 0:
            absent_drop_rate = round((prev_absent_emp_count - current_absent_emp_count) / prev_absent_emp_count * 100, 1)
        else:
            absent_drop_rate = 0.0

        employee_growth_rate = 0.0 # 季度員工增長率暫不計算，保持0
        
        monthly_attendance_rate = current_quarter_attendance
        absent_emp_count = current_absent_emp_count
        monthly_abnormal_count = current_abnormal_count

    elif mode == 'month':
        # 按月模式：與上個月對比
        if start_date.month == 1:
            prev_year = start_date.year - 1
            prev_month = 12
        else:
            prev_year = start_date.year
            prev_month = start_date.month - 1
            
        prev_start_date, prev_end_date = get_month_range(f"{prev_year}-{prev_month:02d}")
        
        # 1. 上月出勤率
        prev_month_days = get_working_days(prev_start_date, prev_end_date)
        prev_attendance_rate = 0.0
        if active_emp_count > 0 and prev_month_days > 0:
            prev_att_count = Attendance.query.filter(
                Attendance.emp_id.in_(active_emp_ids),
                Attendance.att_date.between(prev_start_date, prev_end_date),
                Attendance.is_absent == 0
            ).count()
            prev_attendance_rate = round(prev_att_count / (active_emp_count * prev_month_days) * 100, 1)
            
        if prev_attendance_rate > 0:
            attendance_growth_rate = round((monthly_attendance_rate - prev_attendance_rate) / prev_attendance_rate * 100, 1)
        else:
            attendance_growth_rate = 0.0
            
        # 2. 異常次數
        prev_abnormal_count = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id.in_(active_emp_ids),
            AbnormalAttendance.abnormal_date.between(prev_start_date, prev_end_date)
        ).outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date)) \
         .filter(abnormal_cond).count()
         
        # 异常次数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_abnormal_count > 0:
            abnormal_drop_rate = round((prev_abnormal_count - monthly_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_drop_rate = 0.0
            
        # 3. 曠工人數
        prev_absent_emp_count = 0
        if active_emp_ids:
            prev_absent_result = Attendance.query.filter(
                Attendance.emp_id.in_(active_emp_ids),
                Attendance.att_date.between(prev_start_date, prev_end_date),
                Attendance.is_absent == 1
            ).with_entities(Attendance.emp_id).distinct().all()
            prev_absent_emp_count = len({row[0] for row in prev_absent_result})
        
        # 旷工人数下降率（正值表示下降=好，负值表示上升=坏）
        if prev_absent_emp_count > 0:
            absent_drop_rate = round((prev_absent_emp_count - absent_emp_count) / prev_absent_emp_count * 100, 1)
        else:
            absent_drop_rate = 0.0
        # 月度員工增長率暫不計算
        employee_growth_rate = 0.0

    # 组装响应数据
    data = {
        "empCount": total_emp_count,
        "attendance": f"{monthly_attendance_rate}%",
        "abnormal": monthly_abnormal_count,
        "absent": absent_emp_count,
        "trendData": trend_data,
        "deptAbnormalData": dept_abnormal_data,
        "abnormalTypeData": abnormal_type_data,
        "abnormalRecords": formatted_records,
        "warningList": get_warning_list(start_date, end_date, sys_config), # 新增预警列表
        "exceptionReviewTime": float(sys_config.get('exceptionReviewTime', 24)), # 审核时效
        # 真实计算的趋势率
        "employeeGrowthRate": employee_growth_rate,
        "attendanceGrowthRate": attendance_growth_rate,
        "abnormalDropRate": abnormal_drop_rate,
        "absentDropRate": absent_drop_rate,
        "mode": mode  # 添加模式标识供前端判断
    }
    return api_response(200, "全平台数据查询成功", data)
