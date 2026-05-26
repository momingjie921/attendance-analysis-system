# api/department_api.py
from datetime import date, datetime, timedelta
from flask import request, jsonify, session
from sqlalchemy import and_, or_, func

from models import db, Department, Employee, Attendance, AbnormalAttendance, AbnormalTypeEnum, SystemConfig
from utils.decorators import api_role_required
from utils.cache_utils import cached
from utils.api_helpers import get_month_range, get_working_days, api_response, ABNORMAL_TYPE_CN

@api_role_required(["admin", "manager"])
@cached(timeout=600, key_prefix='dept')
def get_dept_data():
    # 获取参数
    dept_code = request.args.get('dept_code', 'all')
    month = request.args.get('month')
    year = request.args.get('year')
    quarter = request.args.get('quarter')  # expected values: 'Q1','Q2','Q3','Q4'
    current_date = date.today()

    # 日期格式校验
    try:
        if quarter and year:
            # 季度模式
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
            # 年度模式
            y = int(year)
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
            mode = 'year'
        else:
            # 月度模式
            month = month or datetime.now().strftime('%Y-%m')
            start_date, end_date = get_month_range(month)
            mode = 'month'
    except Exception as e:
        return api_response(400, f"日期格式错误：{str(e)}")

    # 全部部门 = 返回空数据提示不支持
    if dept_code == 'all':
        return api_response(400, "请选择具体部门进行查询")

    # 获取指定部门
    dept = Department.query.filter_by(dept_code=dept_code, status=1).first()
    if not dept:
        return api_response(404, "部门不存在")

    # 1. 部门员工数（在职）
    dept_emp_count = dept.employees.filter_by(status=1).count()
    dept_emp_ids = [emp.emp_id for emp in dept.employees if emp.status == 1]
    month_days = get_working_days(start_date, end_date)

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

    # 2. 本月出勤率
    dept_attendance = "0.0%"
    if dept_emp_count > 0 and month_days > 0:
        attendance_count = Attendance.query.filter(
            Attendance.emp_id.in_(dept_emp_ids),
            Attendance.att_date.between(start_date, end_date),
            Attendance.is_absent == 0
        ).count()
        attendance_rate = round(attendance_count / (dept_emp_count * month_days) * 100, 1)
        dept_attendance = f"{attendance_rate}%"

    # 3. 本月异常次数
    dept_abnormal = 0
    if dept_emp_ids:
        dept_abnormal = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id.in_(dept_emp_ids),
                AbnormalAttendance.abnormal_date.between(start_date, end_date),
            )
            .outerjoin(
                Attendance,
                (AbnormalAttendance.emp_id == Attendance.emp_id)
                & (AbnormalAttendance.abnormal_date == Attendance.att_date),
            )
            .filter(abnormal_cond)
            .count()
        )

    # 4. 旷工人数
    absent_emp_count = Attendance.query.filter(
        Attendance.emp_id.in_(dept_emp_ids),
        Attendance.att_date.between(start_date, end_date),
        Attendance.is_absent == 1
    ).with_entities(Attendance.emp_id).distinct().count()

    # 5. 部门月度出勤率趋势
    dept_trend_data = []
    selected_year = start_date.year
    
    if mode == 'quarter':
        # 季度模式：返回12个月的数据，但只统计选中季度的月份
        q_months = []
        cur = start_date
        while cur <= end_date:
            if cur.month not in q_months:
                q_months.append(cur.month)
            cur += timedelta(days=1)
        
        # 生成12个月的数据
        for m in range(1, 13):
            calc_start = date(selected_year, m, 1)
            next_month = date(selected_year + 1, 1, 1) if m == 12 else date(selected_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                calc_att_count = Attendance.query.filter(
                    Attendance.emp_id.in_(dept_emp_ids),
                    Attendance.att_date.between(calc_start, calc_end),
                    Attendance.is_absent == 0
                ).count()
                rate = round(calc_att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)
    elif mode == 'year':
        # 年度模式：返回12个月的数据
        for m in range(1, 13):
            calc_start = date(selected_year, m, 1)
            next_month = date(selected_year + 1, 1, 1) if m == 12 else date(selected_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                calc_att_count = Attendance.query.filter(
                    Attendance.emp_id.in_(dept_emp_ids),
                    Attendance.att_date.between(calc_start, calc_end),
                    Attendance.is_absent == 0
                ).count()
                rate = round(calc_att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)
    else:
        # 月度模式：返回过去12个月的数据
        current_year, current_month = map(int, month.split('-'))
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
            if dept_emp_count > 0 and calc_month_days > 0:
                calc_att_count = Attendance.query.filter(
                    Attendance.emp_id.in_(dept_emp_ids),
                    Attendance.att_date.between(calc_start, calc_end),
                    Attendance.is_absent == 0
                ).count()
                rate = round(calc_att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)

    # 6. 部门异常类型分布
    abnormal_type_counts = {
        AbnormalTypeEnum.LATE: 0,
        AbnormalTypeEnum.EARLY: 0,
        AbnormalTypeEnum.ABSENT: 0,
        AbnormalTypeEnum.MISSING_CHECK: 0,
    }
    if dept_emp_ids:
        type_rows = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id.in_(dept_emp_ids),
                AbnormalAttendance.abnormal_date.between(start_date, end_date),
            )
            .outerjoin(
                Attendance,
                (AbnormalAttendance.emp_id == Attendance.emp_id)
                & (AbnormalAttendance.abnormal_date == Attendance.att_date),
            )
            .filter(abnormal_cond)
            .with_entities(AbnormalAttendance.abnormal_type)
            .all()
        )
        for row in type_rows:
            abn_type = row[0]
            if abn_type in abnormal_type_counts:
                abnormal_type_counts[abn_type] += 1

    abnormal_type_data = []
    for abn_type, count in abnormal_type_counts.items():
        type_name = ABNORMAL_TYPE_CN.get(abn_type.value, abn_type.value)
        abnormal_type_data.append({"name": type_name, "value": count})

    # 7. 部门员工出勤率排名（前5）
    employee_rank = []
    for emp in dept.employees.filter_by(status=1):
        # 本月出勤天数
        emp_att_days = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.between(start_date, end_date),
            Attendance.is_absent == 0
        ).count()
        # 出勤率
        emp_att_rate = round(emp_att_days / month_days * 100, 1) if month_days > 0 else 0
        # 异常次数
        emp_abn_count = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id == emp.emp_id,
                AbnormalAttendance.abnormal_date.between(start_date, end_date),
            )
            .outerjoin(
                Attendance,
                (AbnormalAttendance.emp_id == Attendance.emp_id)
                & (AbnormalAttendance.abnormal_date == Attendance.att_date),
            )
            .filter(abnormal_cond)
            .count()
        )
        # 累计迟到时长
        emp_late_total = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.between(start_date, end_date)
        ).with_entities(
            db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))
        ).scalar() or 0

        employee_rank.append({
            "name": emp.emp_name,
            "attendanceRate": f"{emp_att_rate}%",
            "abnormalCount": emp_abn_count,
            "lateTime": emp_late_total
        })

    # 按出勤率降序排序，取前5
    employee_rank.sort(key=lambda x: float(x['attendanceRate'].replace('%', '')), reverse=True)
    employee_rank = employee_rank[:5]
    # 添加排名
    for idx, item in enumerate(employee_rank, 1):
        item['rank'] = idx

    # ========== 計算與去年/上期的對比數據 ==========
    employee_growth_rate = 0.0
    attendance_growth_rate = 0.0
    abnormal_drop_rate = 0.0
    absent_drop_rate = 0.0

    # 辅助函数：获取指定范围内各月的分组统计
    def get_aggregated_data(start_d, end_d, ids):
        if not ids: return {}
        results = db.session.query(
            func.date_format(Attendance.att_date, '%Y-%m').label('month'),
            func.count(Attendance.att_id).label('count')
        ).filter(
            Attendance.emp_id.in_(ids),
            Attendance.att_date.between(start_d, end_d),
            Attendance.is_absent == 0
        ).group_by(func.date_format(Attendance.att_date, '%Y-%m')).all()
        return {r.month: r.count for r in results}

    # 辅助函数：计算异常次数（考虑阈值）
    def get_abnormal_count(start_d, end_d, ids):
        if not ids: return 0
        return (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id.in_(ids),
                AbnormalAttendance.abnormal_date.between(start_d, end_d),
            )
            .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
            .filter(abnormal_cond).count()
        )

    # 辅助函数：计算旷工去重人数
    def get_absent_unique_count(start_d, end_d, ids):
        if not ids: return 0
        return Attendance.query.filter(
            Attendance.emp_id.in_(ids),
            Attendance.att_date.between(start_d, end_d),
            Attendance.is_absent == 1
        ).with_entities(Attendance.emp_id).distinct().count()

    if mode == 'year':
        # 按年模式：與去年同期對比
        prev_year = start_date.year - 1
        if start_date.year == current_date.year:
            compare_end_month = current_date.month
            compare_end_date = current_date
            # 处理 2月29日 的特殊情况
            try:
                prev_compare_end_date = date(prev_year, current_date.month, current_date.day)
            except ValueError:
                prev_compare_end_date = date(prev_year, current_date.month, current_date.day - 1)
        else:
            compare_end_month = 12
            compare_end_date = end_date
            prev_compare_end_date = date(prev_year, 12, 31)
        
        # 预取聚合数据
        current_year_data = get_aggregated_data(date(start_date.year, 1, 1), end_date, dept_emp_ids)
        prev_year_data = get_aggregated_data(date(prev_year, 1, 1), prev_compare_end_date, dept_emp_ids)

        # 趋势图数据 (12个月)
        dept_trend_data = []
        for m in range(1, 13):
            calc_month_str = f"{start_date.year}-{m:02d}"
            calc_start = date(start_date.year, m, 1)
            next_m = date(start_date.year + 1, 1, 1) if m == 12 else date(start_date.year, m + 1, 1)
            calc_end = next_m - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                att_count = current_year_data.get(calc_month_str, 0)
                rate = round(att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)
        
        # 当前平均出勤率 (仅计已过月份)
        compare_months = range(1, compare_end_month + 1)
        current_rates = [dept_trend_data[m-1] for m in compare_months if dept_trend_data[m-1] > 0]
        current_avg_attendance = round(sum(current_rates) / len(current_rates), 1) if current_rates else 0.0

        # 去年同期平均出勤率
        prev_rates = []
        for m in compare_months:
            calc_month_str = f"{prev_year}-{m:02d}"
            calc_start = date(prev_year, m, 1)
            next_m = date(prev_year + 1, 1, 1) if m == 12 else date(prev_year, m + 1, 1)
            calc_end = next_m - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                att_count = prev_year_data.get(calc_month_str, 0)
                rate = round(att_count / (dept_emp_count * calc_month_days) * 100, 1)
            prev_rates.append(rate)
        valid_prev_rates = [r for r in prev_rates if r > 0]
        prev_avg_attendance = round(sum(valid_prev_rates) / len(valid_prev_rates), 1) if valid_prev_rates else 0.0

        # 异常与旷工
        current_abnormal_count = get_abnormal_count(date(start_date.year, 1, 1), compare_end_date, dept_emp_ids)
        prev_abnormal_count = get_abnormal_count(date(prev_year, 1, 1), prev_compare_end_date, dept_emp_ids)
        current_absent_emp_count = get_absent_unique_count(date(start_date.year, 1, 1), compare_end_date, dept_emp_ids)
        prev_absent_emp_count = get_absent_unique_count(date(prev_year, 1, 1), prev_compare_end_date, dept_emp_ids)

        # 趋势率计算
        if prev_avg_attendance > 0:
            attendance_growth_rate = round((current_avg_attendance - prev_avg_attendance) / prev_avg_attendance * 100, 1)
        else:
            attendance_growth_rate = 0.0
        if prev_abnormal_count > 0:
            abnormal_drop_rate = round((prev_abnormal_count - current_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_drop_rate = 0.0
        if prev_absent_emp_count > 0:
            absent_drop_rate = round((prev_absent_emp_count - current_absent_emp_count) / prev_absent_emp_count * 100, 1)
        else:
            absent_drop_rate = 0.0

        employee_growth_rate = 0.0 # 部门员工数对比简化处理
        dept_attendance = f"{current_avg_attendance}%"
        dept_abnormal = current_abnormal_count
        absent_emp_count = current_absent_emp_count

    elif mode == 'quarter':
        # 按季度模式：與上季度對比
        q = quarter.upper()
        if q == 'Q1':
            prev_start, prev_end = date(start_date.year - 1, 10, 1), date(start_date.year - 1, 12, 31)
        elif q == 'Q2':
            prev_start, prev_end = date(start_date.year, 1, 1), date(start_date.year, 3, 31)
        elif q == 'Q3':
            prev_start, prev_end = date(start_date.year, 4, 1), date(start_date.year, 6, 30)
        else:
            prev_start, prev_end = date(start_date.year, 7, 1), date(start_date.year, 9, 30)

        # 趋势图数据 (12个月)
        year_data = get_aggregated_data(date(start_date.year, 1, 1), date(start_date.year, 12, 31), dept_emp_ids)
        dept_trend_data = []
        for m in range(1, 13):
            calc_start = date(start_date.year, m, 1)
            next_m = date(start_date.year + 1, 1, 1) if m == 12 else date(start_date.year, m + 1, 1)
            calc_end = next_m - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                att_count = year_data.get(f"{start_date.year}-{m:02d}", 0)
                rate = round(att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)

        # 当前季度出勤率
        q_months = range(start_date.month, end_date.month + 1)
        current_rates = [dept_trend_data[m-1] for m in q_months if dept_trend_data[m-1] > 0]
        current_avg_attendance = round(sum(current_rates) / len(current_rates), 1) if current_rates else 0.0

        # 上季度出勤率
        prev_data = get_aggregated_data(prev_start, prev_end, dept_emp_ids)
        prev_rates = []
        cur_m = prev_start.month
        for _ in range(3):
            calc_start = date(prev_start.year, cur_m, 1)
            next_m = date(prev_start.year + 1, 1, 1) if cur_m == 12 else date(prev_start.year, cur_m + 1, 1)
            calc_end = next_m - timedelta(days=1)
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                att_count = prev_data.get(f"{prev_start.year}-{cur_m:02d}", 0)
                rate = round(att_count / (dept_emp_count * calc_month_days) * 100, 1)
            prev_rates.append(rate)
            cur_m = 1 if cur_m == 12 else cur_m + 1
        valid_prev_rates = [r for r in prev_rates if r > 0]
        prev_avg_attendance = round(sum(valid_prev_rates) / len(valid_prev_rates), 1) if valid_prev_rates else 0.0

        # 异常与旷工
        prev_abnormal_count = get_abnormal_count(prev_start, prev_end, dept_emp_ids)
        prev_absent_emp_count = get_absent_unique_count(prev_start, prev_end, dept_emp_ids)

        # 趋势率计算
        attendance_growth_rate = round((current_avg_attendance - prev_avg_attendance) / prev_avg_attendance * 100, 1) if prev_avg_attendance > 0 else 0.0
        abnormal_drop_rate = round((prev_abnormal_count - dept_abnormal) / prev_abnormal_count * 100, 1) if prev_abnormal_count > 0 else 0.0
        absent_drop_rate = round((prev_absent_emp_count - absent_emp_count) / prev_absent_emp_count * 100, 1) if prev_absent_emp_count > 0 else 0.0
        employee_growth_rate = 0.0
        dept_attendance = f"{current_avg_attendance}%"

    else:
        # 按月模式：與上月對比
        current_year, current_month = map(int, month.split('-'))
        prev_year, prev_month = (current_year - 1, 12) if current_month == 1 else (current_year, current_month - 1)
        prev_start_date, prev_end_date = get_month_range(f"{prev_year}-{prev_month:02d}")

        # 趋势图数据 (过去12个月)
        trend_start_date = date(current_year - (1 if current_month <= 11 else 0), (current_month - 11 + 12) % 12 or 12, 1)
        past_data = get_aggregated_data(trend_start_date, end_date, dept_emp_ids)
        dept_trend_data = []
        for i in range(11, -1, -1):
            m = current_month - i
            y = current_year
            if m <= 0: m += 12; y -= 1
            calc_start, calc_end = get_month_range(f"{y}-{m:02d}")
            calc_month_days = get_working_days(calc_start, calc_end)
            rate = 0.0
            if dept_emp_count > 0 and calc_month_days > 0:
                att_count = past_data.get(f"{y}-{m:02d}", 0)
                rate = round(att_count / (dept_emp_count * calc_month_days) * 100, 1)
            dept_trend_data.append(rate)

        # 上月出勤率
        prev_month_days = get_working_days(prev_start_date, prev_end_date)
        prev_att_count = Attendance.query.filter(
            Attendance.emp_id.in_(dept_emp_ids),
            Attendance.att_date.between(prev_start_date, prev_end_date),
            Attendance.is_absent == 0
        ).count()
        prev_attendance_rate = round(prev_att_count / (dept_emp_count * prev_month_days) * 100, 1) if dept_emp_count > 0 and prev_month_days > 0 else 0.0

        # 上月异常与旷工
        prev_abnormal_count = get_abnormal_count(prev_start_date, prev_end_date, dept_emp_ids)
        prev_absent_emp_count = get_absent_unique_count(prev_start_date, prev_end_date, dept_emp_ids)

        # 趋势率计算
        current_rate_val = round(float(dept_attendance.replace('%', '')), 1)
        attendance_growth_rate = round((current_rate_val - prev_attendance_rate) / prev_attendance_rate * 100, 1) if prev_attendance_rate > 0 else 0.0
        abnormal_drop_rate = round((prev_abnormal_count - dept_abnormal) / prev_abnormal_count * 100, 1) if prev_abnormal_count > 0 else 0.0
        absent_drop_rate = round((prev_absent_emp_count - absent_emp_count) / prev_absent_emp_count * 100, 1) if prev_absent_emp_count > 0 else 0.0
        employee_growth_rate = 0.0

    # 组装响应数据
    data = {
        "empCount": dept_emp_count,
        "attendance": dept_attendance,
        "abnormal": dept_abnormal,
        "absent": absent_emp_count,
        "trendData": dept_trend_data,
        "abnormalTypeData": abnormal_type_data,
        "employeeRank": employee_rank,
        # 真实计算的趋势率
        "empGrowthRate": employee_growth_rate,
        "attendanceGrowthRate": attendance_growth_rate,
        "abnormalDropRate": abnormal_drop_rate,
        "absentDropRate": absent_drop_rate
    }
    return api_response(200, f"{dept.dept_name}数据查询成功", data)
