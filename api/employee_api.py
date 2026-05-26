# api/employee_api.py
from datetime import date, datetime, timedelta
from flask import request, jsonify, session
from sqlalchemy import or_, and_
from models import db, Employee, Attendance, AbnormalAttendance, AbnormalTypeEnum, SystemConfig
from utils.decorators import api_role_required
from utils.api_helpers import get_month_range, api_response, ABNORMAL_TYPE_CN, get_working_days, get_working_dates

from utils.pagination import paginate_query, api_paginated_response

@api_role_required(["admin", "manager", "employee"])
def get_employee_data():
    # 获取参数
    keyword = request.args.get('keyword', '')
    month = request.args.get('month')
    year = request.args.get('year')
    quarter = request.args.get('quarter')  # expected values: 'Q1','Q2','Q3','Q4'
    current_role = session.get('role')

    # 日期格式校验和模式判断
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

    # 确定目标员工
    current_emp_id = session.get('emp_id')
    
    if current_role == 'employee':
        # 员工仅能查询自己
        if not current_emp_id:
            return api_response(401, "未获取到员工ID，请重新登录")
        emp = Employee.query.filter_by(emp_id=current_emp_id, status=1).first()
        if not emp:
            return api_response(404, "当前员工信息不存在")
    else:
        # 管理员/经理模式
        if keyword:
            # 搜索员工（姓名/工号模糊匹配）
            candidates = Employee.query.filter(
                db.or_(Employee.emp_name.like(f"%{keyword}%"), Employee.emp_code.like(f"%{keyword}%")),
                Employee.status == 1
            ).all()
            
            if not candidates:
                return api_response(404, "未找到该员工")
                
            if len(candidates) == 1:
                emp = candidates[0]
            else:
                # 如果匹配到多个，优先检查是否有精确匹配工号的
                exact_code_match = next((e for e in candidates if e.emp_code == keyword), None)
                if exact_code_match:
                    emp = exact_code_match
                else:
                    # 如果没有精确匹配工号，则提示用户
                    preview = "、".join([f"{e.emp_name}({e.emp_code})" for e in candidates[:3]])
                    if len(candidates) > 3:
                        preview += " 等"
                    return api_response(400, f"找到多名匹配员工：{preview}。请直接输入工号进行查找。")
        else:
            # 默认查询自己（经理/管理员也可以看自己的数据）
            if not current_emp_id:
                return api_response(401, "未获取到登录信息，请重新登录")
            emp = Employee.query.filter_by(emp_id=current_emp_id, status=1).first()
            if not emp:
                return api_response(404, "当前用户信息不存在")

    # 计算当期已过的工作日天数（用于出勤率分母）
    calc_end_date = min(end_date, date.today())
    working_dates = get_working_dates(start_date, calc_end_date) if start_date <= calc_end_date else []
    month_days = len(working_dates)

    # 加载系统配置
    sys_config = {}
    try:
        configs = SystemConfig.query.all()
        sys_config = {c.config_key: c.config_value for c in configs}
    except Exception:
        pass

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

    # 1. 出勤天数
    attend_days = 0
    if working_dates:
        attend_days = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(working_dates),
            Attendance.is_absent == 0
        ).count()

    # 2. 出勤率
    attendance_rate = round(attend_days / month_days * 100, 1) if month_days > 0 else 0.0
    attendance_str = f"{attendance_rate}%"

    # 3. 异常次数
    abnormal_count = (
        AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id == emp.emp_id,
            AbnormalAttendance.abnormal_date.in_(working_dates) if working_dates else AbnormalAttendance.abnormal_date.between(start_date, calc_end_date),
        )
        .outerjoin(
            Attendance,
            (AbnormalAttendance.emp_id == Attendance.emp_id)
            & (AbnormalAttendance.abnormal_date == Attendance.att_date),
        )
        .filter(abnormal_cond)
        .count()
    )

    # 4. 累计迟到时长
    total_late_minutes = Attendance.query.filter(
        Attendance.emp_id == emp.emp_id,
        Attendance.att_date.in_(working_dates) if working_dates else Attendance.att_date.between(start_date, calc_end_date)
    ).with_entities(
        db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))
    ).scalar() or 0
    late_time_str = f"{total_late_minutes}"

    # 5. 个人打卡趋势 (原有逻辑保留，但增加出勤率趋势)
    checkin_data = []
    checkout_data = []

    # 新增：近12个月出勤率趋势
    attendance_trend_months = []
    attendance_trend_rates = []
    
    # 计算过去12个月（包括当前月）
    end_month_date = date.today().replace(day=1)
    
    # 生成过去12个月的列表
    trend_months = []
    curr = end_month_date
    for _ in range(12):
        trend_months.insert(0, curr)
        # 减去一个月
        first = curr.replace(day=1)
        prev_month_last = first - timedelta(days=1)
        curr = prev_month_last.replace(day=1)

    for m_date in trend_months:
        # 获取该月起止日期
        m_start = m_date
        if m_date.month == 12:
            m_end = date(m_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            m_end = date(m_date.year, m_date.month + 1, 1) - timedelta(days=1)
        
        m_end_limit = m_end
        if m_start.year == date.today().year and m_start.month == date.today().month:
            m_end_limit = min(m_end, date.today())

        m_working_dates = get_working_dates(m_start, m_end_limit) if m_start <= m_end_limit else []
        m_total_days = len(m_working_dates)

        m_attend_days = 0
        if m_working_dates:
            m_attend_days = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(m_working_dates),
                Attendance.is_absent == 0
            ).count()
        
        rate = 0.0
        # 修正分母逻辑：
        # 如果是过去月份，分母 = m_total_days
        # 如果是当前月份，分母 = (today - m_start).days + 1 (截止到今天)
        # 如果是未来月份(不应该出现在这里，因为是从today倒推的)，则为0
        
        denominator = m_total_days
        if denominator > 0:
            rate = round(m_attend_days / denominator * 100, 1)
        
        attendance_trend_months.append(f"{m_date.month}月")
        attendance_trend_rates.append(rate)


    if mode == 'year':
        # 按年模式：计算每个月的平均打卡时间
        year_int = int(year) if year else datetime.now().year
        for m in range(1, 13):
            month_start = date(year_int, m, 1)
            next_month_date = date(year_int + 1, 1, 1) if m == 12 else date(year_int, m + 1, 1)
            month_end = next_month_date - timedelta(days=1)
            
            # 查询当月所有打卡记录
            attendances = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.between(month_start, month_end),
                Attendance.is_absent == 0
            ).all()
            
            if not attendances:
                checkin_data.append(None)
                checkout_data.append(None)
                continue
                
            total_in = 0
            total_out = 0
            count_in = 0
            count_out = 0
            
            for att in attendances:
                if att.check_in_time:
                    total_in += att.check_in_time.hour + att.check_in_time.minute / 60
                    count_in += 1
                if att.check_out_time:
                    total_out += att.check_out_time.hour + att.check_out_time.minute / 60
                    count_out += 1
            
            avg_in = round(total_in / count_in, 1) if count_in > 0 else None
            avg_out = round(total_out / count_out, 1) if count_out > 0 else None
            checkin_data.append(avg_in)
            checkout_data.append(avg_out)

    elif mode == 'quarter':
        # 按季度模式：计算该季度每个月的平均打卡时间
        q_months = []
        curr = start_date
        # 获取该季度的月份列表
        while curr <= end_date:
            if curr.month not in q_months:
                q_months.append(curr.month)
            # 跳到下个月
            next_month_date = date(curr.year + 1, 1, 1) if curr.month == 12 else date(curr.year, curr.month + 1, 1)
            curr = next_month_date
            
        for m in q_months:
            month_start = date(start_date.year, m, 1)
            next_month_date = date(start_date.year + 1, 1, 1) if m == 12 else date(start_date.year, m + 1, 1)
            month_end = next_month_date - timedelta(days=1)
            
            attendances = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.between(month_start, month_end),
                Attendance.is_absent == 0
            ).all()
            
            if not attendances:
                checkin_data.append(None)
                checkout_data.append(None)
                continue
                
            total_in = 0
            total_out = 0
            count_in = 0
            count_out = 0
            
            for att in attendances:
                if att.check_in_time:
                    total_in += att.check_in_time.hour + att.check_in_time.minute / 60
                    count_in += 1
                if att.check_out_time:
                    total_out += att.check_out_time.hour + att.check_out_time.minute / 60
                    count_out += 1
            
            avg_in = round(total_in / count_in, 1) if count_in > 0 else None
            avg_out = round(total_out / count_out, 1) if count_out > 0 else None
            checkin_data.append(avg_in)
            checkout_data.append(avg_out)
            
    else:
        # 按月/季度模式：返回每一天的实际打卡时间
        curr = start_date
        while curr <= end_date:
            att = Attendance.query.filter_by(
                emp_id=emp.emp_id,
                att_date=curr
            ).first()

            # 上班打卡时间
            if att and att.check_in_time:
                checkin_hour = att.check_in_time.hour + att.check_in_time.minute / 60
                checkin_data.append(round(checkin_hour, 1))
            else:
                checkin_data.append(None)

            # 下班打卡时间
            if att and att.check_out_time:
                checkout_hour = att.check_out_time.hour + att.check_out_time.minute / 60
                checkout_data.append(round(checkout_hour, 1))
            else:
                checkout_data.append(None)
            
            curr += timedelta(days=1)

    # 6. 个人异常类型分布
    abnormal_type_data = []
    for abn_type in AbnormalTypeEnum:
        query = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id == emp.emp_id,
            AbnormalAttendance.abnormal_date.between(start_date, end_date),
            AbnormalAttendance.abnormal_type == abn_type
        )
        
        # 加入阈值过滤
        if abn_type == AbnormalTypeEnum.LATE:
            query = query.join(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
            query = query.filter(or_(Attendance.late_minutes.is_(None), Attendance.late_minutes > late_threshold))
        elif abn_type == AbnormalTypeEnum.EARLY:
            query = query.join(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
            query = query.filter(or_(Attendance.early_minutes.is_(None), Attendance.early_minutes > early_threshold))
            
        type_count = query.count()

        # 使用中文名称
        type_name = ABNORMAL_TYPE_CN.get(abn_type.value, abn_type.value)
        abnormal_type_data.append({
            "name": type_name,
            "value": type_count
        })

    # 7. 个人异常明细
    abnormal_detail = AbnormalAttendance.query.filter(
        AbnormalAttendance.emp_id == emp.emp_id,
        AbnormalAttendance.abnormal_date.between(start_date, end_date)
    ).join(Attendance,
           (AbnormalAttendance.emp_id == Attendance.emp_id) &
           (AbnormalAttendance.abnormal_date == Attendance.att_date)
           ).filter(abnormal_cond).with_entities(
        AbnormalAttendance.abnormal_date,
        AbnormalAttendance.abnormal_type,
        db.case(
            (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.LATE, Attendance.check_in_time),
            (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.EARLY, Attendance.check_out_time),
            else_=None
        ).label('check_time'),
        db.case(
            (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.LATE, Attendance.late_minutes),
            (AbnormalAttendance.abnormal_type == AbnormalTypeEnum.EARLY, Attendance.early_minutes),
            else_=0
        ).label('duration'),
        AbnormalAttendance.abnormal_desc,
        AbnormalAttendance.is_processed,
        AbnormalAttendance.update_time,
        AbnormalAttendance.process_remark,
        AbnormalAttendance.abnormal_id, # Added ID
        AbnormalAttendance.create_time # Added create_time for timeout check
    ).order_by(AbnormalAttendance.abnormal_date.desc()).all()

    formatted_detail = []
    for rec in abnormal_detail:
        abn_date, abn_type, check_time, duration, abn_desc, is_processed, update_time, process_remark, abn_id, create_time = rec
        
        status_text = "待处理"
        status_class = "badge-warning"
        display_remark = abn_desc or "-"
        
        if is_processed:
            status_text = "已处理"
            status_class = "badge-success"
            raw_remark = process_remark or ""
            
            if raw_remark.startswith("[WARN]"):
                status_text = "已警告"
                status_class = "badge-warned"
                display_remark = raw_remark[6:].strip() or abn_desc or "-"
            elif raw_remark.startswith("[MAKEUP]"):
                status_text = "已补假"
                status_class = "badge-makeup"
                display_remark = raw_remark[8:].strip() or abn_desc or "-"
            elif raw_remark.startswith("[APPROVED]"):
                status_text = "已批准"
                status_class = "badge-approved"
                display_remark = raw_remark[10:].strip() or abn_desc or "-"
            elif raw_remark.startswith("[REJECTED]"):
                status_text = "已驳回"
                status_class = "badge-rejected"
                display_remark = raw_remark[10:].strip() or abn_desc or "-"
            else:
                display_remark = raw_remark or abn_desc or "-"

        formatted_detail.append({
            "date": abn_date.strftime('%Y-%m-%d'),
            "type": ABNORMAL_TYPE_CN.get(abn_type.value, abn_type.value),
            "checkinTime": check_time.strftime('%H:%M:%S') if check_time else '-',
            "duration": duration,
            "remark": display_remark,
            "status": status_text,
            "statusClass": status_class,
            "processTime": update_time.strftime('%Y-%m-%d %H:%M') if is_processed == 1 and update_time else '-',
            "processRemark": process_remark or '-',
            "abnormal_id": abn_id,
            "create_time": create_time.strftime('%Y-%m-%d %H:%M:%S') if create_time else ""
        })

    # ========== 計算與去年/上期的對比數據 ==========
    attend_days_growth = 0
    attendance_drop_rate = 0
    abnormal_growth = 0
    late_time_growth = 0

    # 獲取當前日期，用於限制比較範圍
    current_date = date.today()

    if mode == 'year':
        # 按年模式：與去年同期對比
        prev_year = start_date.year - 1

        # 確定當前年已經過了哪些月份
        if start_date.year == current_date.year:
            compare_end_month = current_date.month
        else:
            compare_end_month = 12
        compare_months = range(1, compare_end_month + 1)

        # 計算當年已過月份的天數
        current_total_days = 0
        current_attend_days = 0
        current_abnormal_count = 0
        current_late_minutes = 0
        current_late_count = 0

        for m in compare_months:
            calc_start = date(start_date.year, m, 1)
            next_month = date(start_date.year + 1, 1, 1) if m == 12 else date(start_date.year, m + 1, 1)
            calc_end = min(next_month - timedelta(days=1), end_date)
            calc_working_dates = get_working_dates(calc_start, calc_end) if calc_start <= calc_end else []
            current_total_days += len(calc_working_dates)

            # 出勤天數
            if calc_working_dates:
                current_attend_days += Attendance.query.filter(
                    Attendance.emp_id == emp.emp_id,
                    Attendance.att_date.in_(calc_working_dates),
                    Attendance.is_absent == 0
                ).count()

            # 異常次數
            current_abnormal_count += (
                AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id == emp.emp_id,
                    AbnormalAttendance.abnormal_date.in_(calc_working_dates) if calc_working_dates else AbnormalAttendance.abnormal_date.between(calc_start, calc_end)
                )
                .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
                .filter(abnormal_cond)
                .count()
            )

            # 迟到時長
            current_late_minutes += Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(calc_working_dates) if calc_working_dates else Attendance.att_date.between(calc_start, calc_end)
            ).with_entities(db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))).scalar() or 0

            # 迟到次数
            current_late_count += Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(calc_working_dates) if calc_working_dates else Attendance.att_date.between(calc_start, calc_end),
                Attendance.late_minutes > late_threshold
            ).count()

        # 計算去年同期的數據
        prev_total_days = 0
        prev_attend_days = 0
        prev_abnormal_count = 0
        prev_late_minutes = 0
        prev_late_count = 0

        for m in compare_months:
            calc_start = date(prev_year, m, 1)
            next_month = date(prev_year + 1, 1, 1) if m == 12 else date(prev_year, m + 1, 1)
            calc_end = next_month - timedelta(days=1)
            calc_working_dates = get_working_dates(calc_start, calc_end) if calc_start <= calc_end else []
            prev_total_days += len(calc_working_dates)

            if calc_working_dates:
                prev_attend_days += Attendance.query.filter(
                    Attendance.emp_id == emp.emp_id,
                    Attendance.att_date.in_(calc_working_dates),
                    Attendance.is_absent == 0
                ).count()

            prev_abnormal_count += (
                AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id == emp.emp_id,
                    AbnormalAttendance.abnormal_date.in_(calc_working_dates) if calc_working_dates else AbnormalAttendance.abnormal_date.between(calc_start, calc_end)
                )
                .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
                .filter(abnormal_cond)
                .count()
            )

            prev_late_minutes += Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(calc_working_dates) if calc_working_dates else Attendance.att_date.between(calc_start, calc_end)
            ).with_entities(db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))).scalar() or 0

            prev_late_count += Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(calc_working_dates) if calc_working_dates else Attendance.att_date.between(calc_start, calc_end),
                Attendance.late_minutes > late_threshold
            ).count()

        # 計算增長率
        current_attendance_rate = round(current_attend_days / current_total_days * 100, 1) if current_total_days > 0 else 0.0
        prev_attendance_rate = round(prev_attend_days / prev_total_days * 100, 1) if prev_total_days > 0 else 0.0

        prev_start_date_for_avg = date(prev_year, 1, 1)
        prev_end_date_for_avg = calc_end

        if prev_attend_days > 0:
            attend_days_growth = round((current_attend_days - prev_attend_days) / prev_attend_days * 100, 1)
        else:
            attend_days_growth = 0

        if prev_attendance_rate > 0:
            attendance_drop_rate = round((prev_attendance_rate - current_attendance_rate) / prev_attendance_rate * 100, 1)
        else:
            attendance_drop_rate = 0

        if prev_abnormal_count > 0:
            abnormal_growth = round((current_abnormal_count - prev_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_growth = 0

        if prev_late_minutes > 0:
            late_time_growth = round((current_late_minutes - prev_late_minutes) / prev_late_minutes * 100, 1)
        else:
            late_time_growth = 0

        if prev_late_count > 0:
            late_count_growth = round((current_late_count - prev_late_count) / prev_late_count * 100, 1)
        else:
            late_count_growth = 0

        # 更新数据为当年已过月份的值
        attend_days = current_attend_days
        abnormal_count = current_abnormal_count
        total_late_minutes = current_late_minutes
        late_count = current_late_count
        attendance_str = f"{current_attendance_rate}%"

    elif mode == 'quarter':
        # 按季度模式：與上季度對比
        q = quarter.upper()

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

        prev_total_days = get_working_days(prev_start, prev_end)
        prev_working_dates = get_working_dates(prev_start, prev_end) if prev_start <= prev_end else []
        prev_attend_days = 0
        if prev_working_dates:
            prev_attend_days = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(prev_working_dates),
                Attendance.is_absent == 0
            ).count()
        prev_attendance_rate = round(prev_attend_days / prev_total_days * 100, 1) if prev_total_days > 0 else 0.0

        prev_abnormal_count = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id == emp.emp_id,
                AbnormalAttendance.abnormal_date.in_(prev_working_dates) if prev_working_dates else AbnormalAttendance.abnormal_date.between(prev_start, prev_end)
            )
            .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
            .filter(abnormal_cond)
            .count()
        )

        prev_late_minutes = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(prev_working_dates) if prev_working_dates else Attendance.att_date.between(prev_start, prev_end)
        ).with_entities(db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))).scalar() or 0

        prev_late_count = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(prev_working_dates) if prev_working_dates else Attendance.att_date.between(prev_start, prev_end),
            Attendance.late_minutes > late_threshold
        ).count()

        # 计算当前季度的出勤率
        # 如果是当前季度，应该只计算已过的天数（这里简单优化：如果是当前季度，使用 attend_days / (today - start)？）
        # 鉴于代码结构，我们这里复用 attend_days (已自动过滤未来日期？不，attend_days 是 filter start-end)
        # Attendance.query ... between(start, end)
        # 如果 end 是未来，数据库里没有记录，attend_days 只是当前有的记录数
        # 但 month_days 是整个季度的天数。
        # 修正：如果是当前季度，分母应该是 min(end_date, today) - start_date
        
        q_end_limit = min(end_date, date.today())
        if q_end_limit >= start_date:
            q_working_dates = get_working_dates(start_date, q_end_limit)
            q_total_days = len(q_working_dates)
            q_attend_days = 0
            if q_working_dates:
                q_attend_days = Attendance.query.filter(
                    Attendance.emp_id == emp.emp_id,
                    Attendance.att_date.in_(q_working_dates),
                    Attendance.is_absent == 0
                ).count()
            current_attendance_rate = round(q_attend_days / q_total_days * 100, 1) if q_total_days > 0 else 0.0
        else:
            current_attendance_rate = 0.0
             
        attendance_str = f"{current_attendance_rate}%"

        prev_start_date_for_avg = prev_start
        prev_end_date_for_avg = prev_end

        # 计算增长率
        if prev_attend_days > 0:
            attend_days_growth = round((attend_days - prev_attend_days) / prev_attend_days * 100, 1)
        else:
            attend_days_growth = 0

        if prev_attendance_rate > 0:
            attendance_drop_rate = round((prev_attendance_rate - current_attendance_rate) / prev_attendance_rate * 100, 1)
        else:
            attendance_drop_rate = 0

        if prev_abnormal_count > 0:
            abnormal_growth = round((abnormal_count - prev_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_growth = 0

        if prev_late_minutes > 0:
            late_time_growth = round((total_late_minutes - prev_late_minutes) / prev_late_minutes * 100, 1)
        else:
            late_time_growth = 0

        # 9. 迟到次数 (Specifically LATE, not just abnormal) - Note: Moved up to calculate late_count before using it
        late_count = 0
        if working_dates:
            late_count = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(working_dates),
                Attendance.late_minutes > late_threshold
            ).count()

        if prev_late_count > 0:
            late_count_growth = round((late_count - prev_late_count) / prev_late_count * 100, 1)
        else:
            late_count_growth = 0

    else:
        # 按月模式：與上月對比
        current_year, current_month = map(int, month.split('-'))

        # 上月時間範圍
        if current_month == 1:
            prev_year = current_year - 1
            prev_month = 12
        else:
            prev_year = current_year
            prev_month = current_month - 1
        prev_start_date, prev_end_date = get_month_range(f"{prev_year}-{prev_month:02d}")
        prev_month_days = get_working_days(prev_start_date, prev_end_date)
        prev_working_dates = get_working_dates(prev_start_date, prev_end_date) if prev_start_date <= prev_end_date else []

        prev_attend_days = 0
        if prev_working_dates:
            prev_attend_days = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(prev_working_dates),
                Attendance.is_absent == 0
            ).count()
        prev_attendance_rate = round(prev_attend_days / prev_month_days * 100, 1) if prev_month_days > 0 else 0.0

        prev_abnormal_count = (
            AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id == emp.emp_id,
                AbnormalAttendance.abnormal_date.in_(prev_working_dates) if prev_working_dates else AbnormalAttendance.abnormal_date.between(prev_start_date, prev_end_date)
            )
            .outerjoin(Attendance, (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date))
            .filter(abnormal_cond)
            .count()
        )

        prev_late_minutes = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(prev_working_dates) if prev_working_dates else Attendance.att_date.between(prev_start_date, prev_end_date)
        ).with_entities(db.func.sum(db.case((Attendance.late_minutes > late_threshold, Attendance.late_minutes), else_=0))).scalar() or 0

        prev_late_count = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(prev_working_dates) if prev_working_dates else Attendance.att_date.between(prev_start_date, prev_end_date),
            Attendance.late_minutes > late_threshold
        ).count()

        prev_start_date_for_avg = prev_start_date
        prev_end_date_for_avg = prev_end_date

        # 計算增長率
        if prev_attend_days > 0:
            attend_days_growth = round((attend_days - prev_attend_days) / prev_attend_days * 100, 1)
        else:
            attend_days_growth = 0

        if prev_attendance_rate > 0:
            attendance_drop_rate = round((prev_attendance_rate - attendance_rate) / prev_attendance_rate * 100, 1)
        else:
            attendance_drop_rate = 0

        if prev_abnormal_count > 0:
            abnormal_growth = round((abnormal_count - prev_abnormal_count) / prev_abnormal_count * 100, 1)
        else:
            abnormal_growth = 0

        if prev_late_minutes > 0:
            late_time_growth = round((total_late_minutes - prev_late_minutes) / prev_late_minutes * 100, 1)
        else:
            late_time_growth = 0

        # 9. 迟到次数 (Specifically LATE, not just abnormal) - Note: Moved up to calculate late_count before using it
        late_count = 0
        if working_dates:
            late_count = Attendance.query.filter(
                Attendance.emp_id == emp.emp_id,
                Attendance.att_date.in_(working_dates),
                Attendance.late_minutes > late_threshold
            ).count()

        if prev_late_count > 0:
            late_count_growth = round((late_count - prev_late_count) / prev_late_count * 100, 1)
        else:
            late_count_growth = 0

    # 10. 平均打卡时间
    # Calculate average check-in time for the current period
    avg_checkin_time_str = "-"
    avg_checkin_seconds = None
    checkin_times = Attendance.query.filter(
        Attendance.emp_id == emp.emp_id,
        Attendance.att_date.in_(working_dates) if working_dates else Attendance.att_date.between(start_date, calc_end_date),
        Attendance.check_in_time.isnot(None)
    ).with_entities(Attendance.check_in_time).all()
    
    if checkin_times:
        total_seconds = 0
        count = 0
        for (ct,) in checkin_times:
            # Calculate seconds from midnight
            seconds = ct.hour * 3600 + ct.minute * 60 + ct.second
            total_seconds += seconds
            count += 1
        
        if count > 0:
            avg_checkin_seconds = int(total_seconds / count)
            avg_hour = avg_checkin_seconds // 3600
            avg_minute = (avg_checkin_seconds % 3600) // 60
            avg_checkin_time_str = f"{avg_hour:02d}:{avg_minute:02d}"

    # Calculate average check-in time difference
    avg_checkin_diff_minutes = None
    if avg_checkin_seconds is not None:
        prev_checkin_times = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(get_working_dates(prev_start_date_for_avg, prev_end_date_for_avg)) if prev_start_date_for_avg and prev_end_date_for_avg and prev_start_date_for_avg <= prev_end_date_for_avg else Attendance.att_date.between(prev_start_date_for_avg, prev_end_date_for_avg),
            Attendance.check_in_time.isnot(None)
        ).with_entities(Attendance.check_in_time).all()

        if prev_checkin_times:
            prev_total_seconds = sum(ct[0].hour * 3600 + ct[0].minute * 60 + ct[0].second for ct in prev_checkin_times)
            prev_avg_checkin_seconds = int(prev_total_seconds / len(prev_checkin_times))
            # positive diff means current is later than previous
            avg_checkin_diff_minutes = round((avg_checkin_seconds - prev_avg_checkin_seconds) / 60)

    # 8. 完整考勤明细（用于前端表格展示）
    attendance_records = Attendance.query.filter(
        Attendance.emp_id == emp.emp_id,
        Attendance.att_date.between(start_date, end_date)
    ).order_by(Attendance.att_date.desc()).all()
    
    attendance_list = []
    # 获取该时间段内的异常记录，用于快速查找备注
    abnormal_map = {
        ab.abnormal_date: ab 
        for ab in AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id == emp.emp_id, 
            AbnormalAttendance.abnormal_date.between(start_date, end_date)
        ).all()
    }
    
    for att in attendance_records:
        status = "正常"
        status_class = "badge-normal" # default green
        remark = "-"
        
        if att.is_absent:
            status = "缺勤"
            status_class = "badge-danger" # need to check if css supports
        elif att.late_minutes > late_threshold:
            status = f"迟到{att.late_minutes}分钟"
            status_class = "badge-warning" # yellow
        elif att.early_minutes > early_threshold:
            status = f"早退{att.early_minutes}分钟"
            status_class = "badge-warning"
        
        # Check abnormal record for more specific status or remark
        ab_rec = abnormal_map.get(att.att_date)
        if ab_rec:
            if ab_rec.abnormal_type == AbnormalTypeEnum.MISSING_CHECK:
                 status = "漏打卡"
                 status_class = "badge-warning"
            if ab_rec.abnormal_desc:
                remark = ab_rec.abnormal_desc
        
        attendance_list.append({
            "date": att.att_date.strftime('%Y-%m-%d'),
            "checkinTime": att.check_in_time.strftime('%H:%M') if att.check_in_time else '-',
            "checkoutTime": att.check_out_time.strftime('%H:%M') if att.check_out_time else '-',
            "status": status,
            "statusClass": status_class,
            "remark": remark
        })

    # 组装响应数据
    data = {
        "empInfo": {
            "empName": emp.emp_name,
            "empCode": emp.emp_code,
            "deptName": emp.department.dept_name if emp.department else "未知部门"
        },
        "attendDays": attend_days,
        "attendance": attendance_str,
        "abnormal": abnormal_count,
        "lateTime": late_time_str,
        "checkinData": checkin_data,
        "checkoutData": checkout_data,
        "attendanceTrendMonths": attendance_trend_months, # 新增
        "attendanceTrendRates": attendance_trend_rates,   # 新增
        "abnormalTypeData": abnormal_type_data,
        "abnormalDetail": formatted_detail,
        "attendanceList": attendance_list, # 新增
        "lateCount": late_count, # 新增
        "avgCheckinTime": avg_checkin_time_str, # 新增
        # 真实计算的趋势率
        "attendDaysGrowth": attend_days_growth,
        "attendanceDropRate": attendance_drop_rate,
        "abnormalGrowth": abnormal_growth,
        "lateTimeGrowth": late_time_growth,
        "lateCountGrowth": late_count_growth,
        "avgCheckinDiffMinutes": avg_checkin_diff_minutes
    }
    return api_response(200, f"{emp.emp_name}个人数据查询成功", data)


def get_date_range_from_request():
    """Helper to extract date range from request params"""
    month = request.args.get('month')
    year = request.args.get('year')
    quarter = request.args.get('quarter')
    
    start_date, end_date = None, None
    mode = 'month'
    
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
            mode = 'quarter'
        elif year:
            y = int(year)
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
            mode = 'year'
        else:
            month = month or datetime.now().strftime('%Y-%m')
            start_date, end_date = get_month_range(month)
            mode = 'month'
            
        return start_date, end_date, mode, None
    except Exception as e:
        return None, None, None, str(e)


def get_current_employee():
    """Helper to get current employee with validation"""
    current_role = session.get('role')
    
    if current_role == 'employee':
        current_emp_id = session.get('emp_id')
        if not current_emp_id:
            return None, "未获取到员工ID，请重新登录"
        emp = Employee.query.filter_by(emp_id=current_emp_id, status=1).first()
        if not emp:
            return None, "当前员工信息不存在"
        return emp, None
    else:
        # Admin/Manager search logic
        target_id = request.args.get('emp_id')
        if target_id:
            emp = Employee.query.get(target_id)
            if emp: return emp, None
            
        keyword = request.args.get('keyword')
        if keyword:
             emp = Employee.query.filter(
                or_(Employee.emp_name == keyword, Employee.emp_code == keyword),
                Employee.status == 1
             ).first()
             if emp: return emp, None
        
        # Default to current user's emp_id from session
        current_emp_id = session.get('emp_id')
        if current_emp_id:
            emp = Employee.query.filter_by(emp_id=current_emp_id, status=1).first()
            if emp: return emp, None
             
        return None, "请提供有效的员工ID或关键词"


@api_role_required(["admin", "manager", "employee"])
def get_attendance_list():
    """获取考勤记录列表（分页）"""
    emp, error = get_current_employee()
    if error: return api_response(401 if "登录" in error else 404, error)
    
    start_date, end_date, mode, err = get_date_range_from_request()
    if err: return api_response(400, f"日期格式错误: {err}")
    
    # 状态筛选
    status_filter = request.args.get('status', 'all')
    
    query = Attendance.query.filter(
        Attendance.emp_id == emp.emp_id,
        Attendance.att_date.between(start_date, end_date)
    )
    
    # Apply filters
    sys_config = {}
    try:
        configs = SystemConfig.query.all()
        sys_config = {c.config_key: c.config_value for c in configs}
    except: pass
    
    late_threshold = int(float(sys_config.get('lateThreshold') or 0))
    early_threshold = int(float(sys_config.get('earlyLeaveThreshold') or 0))

    if status_filter == '正常':
        query = (
            query.outerjoin(
                AbnormalAttendance,
                and_(
                    AbnormalAttendance.emp_id == Attendance.emp_id,
                    AbnormalAttendance.abnormal_date == Attendance.att_date,
                ),
            )
            .filter(
                Attendance.is_absent == 0,
                or_(Attendance.late_minutes.is_(None), Attendance.late_minutes <= late_threshold),
                or_(Attendance.early_minutes.is_(None), Attendance.early_minutes <= early_threshold),
                or_(
                    AbnormalAttendance.abnormal_id.is_(None),
                    AbnormalAttendance.abnormal_type != AbnormalTypeEnum.MISSING_CHECK,
                ),
            )
            .distinct(Attendance.att_id)
        )
    elif status_filter == '迟到':
        query = query.filter(Attendance.late_minutes > late_threshold)
    elif status_filter == '早退':
        query = query.filter(Attendance.early_minutes > early_threshold)
    elif status_filter in ('缺勤', '旷工'):
        query = query.filter(Attendance.is_absent == 1)
    elif status_filter == '漏打卡':
        query = query.join(
            AbnormalAttendance,
            and_(
                AbnormalAttendance.emp_id == Attendance.emp_id,
                AbnormalAttendance.abnormal_date == Attendance.att_date
            )
        ).filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum.MISSING_CHECK).distinct(Attendance.att_id)
    
    # Default sort
    query = query.order_by(Attendance.att_date.desc())
    
    # Pagination
    pagination = paginate_query(query)
    
    # Serialize
    def serialize_attendance(att):
        status = "正常"
        status_class = "badge-normal"
        remark = "-"
        
        if att.is_absent:
            status = "旷工"
            status_class = "badge-danger"
        else:
            late_flag = bool(att.late_minutes and att.late_minutes > late_threshold)
            early_flag = bool(att.early_minutes and att.early_minutes > early_threshold)
            if late_flag and early_flag:
                status_class = "badge-warning"
                if status_filter == "迟到":
                    status = "迟到"
                elif status_filter == "早退":
                    status = "早退"
                else:
                    status = "迟到/早退"
                remark = f"迟到{att.late_minutes}分钟，早退{att.early_minutes}分钟"
            elif late_flag:
                status = "迟到"
                status_class = "badge-warning"
                remark = f"迟到{att.late_minutes}分钟"
            elif early_flag:
                status = "早退"
                status_class = "badge-warning"
                remark = f"早退{att.early_minutes}分钟"
            
        return {
            "date": att.att_date.strftime('%Y-%m-%d'),
            "checkinTime": att.check_in_time.strftime('%H:%M') if att.check_in_time else '-',
            "checkoutTime": att.check_out_time.strftime('%H:%M') if att.check_out_time else '-',
            "status": status,
            "statusClass": status_class,
            "remark": remark,
            "abnormal_id": None
        }
    
    # Batch fetch abnormal remarks for the current page items
    items = pagination.items
    if items:
        dates = [item.att_date for item in items]
        abnormals = AbnormalAttendance.query.filter(
            AbnormalAttendance.emp_id == emp.emp_id,
            AbnormalAttendance.abnormal_date.in_(dates)
        ).all()
        abnormal_map = {a.abnormal_date: a for a in abnormals}
        
        serialized_items = []
        for att in items:
            data = serialize_attendance(att)
            ab = abnormal_map.get(att.att_date)
            if ab:
                data['abnormal_id'] = ab.abnormal_id
                if ab.abnormal_type == AbnormalTypeEnum.MISSING_CHECK:
                    data['status'] = "漏打卡"
                    data['statusClass'] = "badge-warning"
                    if data['remark'] == "-":
                        data['remark'] = ab.abnormal_desc or "漏打卡"
                
                if ab.abnormal_desc:
                    if data['remark'] == "-":
                        data['remark'] = ab.abnormal_desc
                    elif ab.abnormal_desc not in data['remark']:
                        data['remark'] = f"{data['remark']} ({ab.abnormal_desc})"
            
            serialized_items.append(data)
            
        # Override items in pagination dict logic (custom response needed)
        # actually api_paginated_response takes a serializer, but we did batch processing.
        # So we construct dict manually or pass a dummy serializer and replace items.
        
        pag_dict = pagination.to_dict()
        pag_dict['items'] = serialized_items
        return jsonify({'code': 200, 'msg': '查询成功', 'data': pag_dict})

    return api_paginated_response(pagination, serialize_attendance)


@api_role_required(["admin", "manager", "employee"])
def get_abnormal_list_paginated():
    """获取异常记录列表（分页）"""
    emp, error = get_current_employee()
    if error: return api_response(401 if "登录" in error else 404, error)
    
    start_date, end_date, mode, err = get_date_range_from_request()
    if err: return api_response(400, f"日期格式错误: {err}")
    
    type_filter = request.args.get('type', 'all')
    
    query = AbnormalAttendance.query.filter(
        AbnormalAttendance.emp_id == emp.emp_id,
        AbnormalAttendance.abnormal_date.between(start_date, end_date)
    )
    
    if type_filter != 'all':
        # Check if type exists in Enum or use name
        # The frontend sends Chinese "迟到", "早退" etc.
        # Need mapping
        CN_TO_TYPE = {v: k for k, v in ABNORMAL_TYPE_CN.items()}
        # ABNORMAL_TYPE_CN keys are Enum values (int/str)
        # But wait, ABNORMAL_TYPE_CN might be {Enum.LATE: "迟到"} or {1: "迟到"}
        # Let's check api_helpers.py
        pass 
        
        # Simple mapping based on known values
        if type_filter == '迟到': query = query.filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum.LATE)
        elif type_filter == '早退': query = query.filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum.EARLY)
        elif type_filter == '旷工': query = query.filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum.ABSENT)
        elif type_filter == '漏打卡': query = query.filter(AbnormalAttendance.abnormal_type == AbnormalTypeEnum.MISSING_CHECK)
        
    query = query.order_by(AbnormalAttendance.abnormal_date.desc())
    
    # Join Attendance to get duration
    # We can do this in serializer
    
    pagination = paginate_query(query)
    
    # Batch fetch attendance for duration
    items = pagination.items
    att_map = {}
    if items:
        dates = [item.abnormal_date for item in items]
        atts = Attendance.query.filter(
            Attendance.emp_id == emp.emp_id,
            Attendance.att_date.in_(dates)
        ).all()
        att_map = {a.att_date: a for a in atts}

    def serialize_abnormal(abn):
        att = att_map.get(abn.abnormal_date)
        duration = 0
        check_time = None
        
        if abn.abnormal_type == AbnormalTypeEnum.LATE and att:
            duration = att.late_minutes
            check_time = att.check_in_time
        elif abn.abnormal_type == AbnormalTypeEnum.EARLY and att:
            duration = att.early_minutes
            check_time = att.check_out_time
            
        status_text = "待处理"
        status_class = "badge-warning"
        display_remark = abn.abnormal_desc or "-"
        
        if abn.is_processed:
            status_text = "已处理"
            status_class = "badge-success"
            raw_remark = abn.process_remark or ""
            
            if raw_remark.startswith("[WARN]"):
                status_text = "已警告"
                status_class = "badge-warned"
                display_remark = raw_remark[6:].strip() or abn.abnormal_desc or "-"
            elif raw_remark.startswith("[MAKEUP]"):
                status_text = "已补假"
                status_class = "badge-makeup"
                display_remark = raw_remark[8:].strip() or abn.abnormal_desc or "-"
            elif raw_remark.startswith("[APPROVED]"):
                status_text = "已批准"
                status_class = "badge-approved"
                display_remark = raw_remark[10:].strip() or abn.abnormal_desc or "-"
            elif raw_remark.startswith("[REJECTED]"):
                status_text = "已驳回"
                status_class = "badge-rejected"
                display_remark = raw_remark[10:].strip() or abn.abnormal_desc or "-"
            else:
                display_remark = raw_remark or abn.abnormal_desc or "-"

        return {
            "abnormal_id": abn.abnormal_id,
            "date": abn.abnormal_date.strftime('%Y-%m-%d'),
            "type": ABNORMAL_TYPE_CN.get(abn.abnormal_type.value, abn.abnormal_type.value),
            "checkinTime": check_time.strftime('%H:%M:%S') if check_time else '-',
            "duration": duration,
            "remark": display_remark,
            "status": status_text,
            "statusClass": status_class,
            "processTime": abn.update_time.strftime('%Y-%m-%d %H:%M') if abn.is_processed == 1 and abn.update_time else '-',
            "processRemark": abn.process_remark or '-'
        }

    return api_paginated_response(pagination, serialize_abnormal)


@api_role_required(["admin", "manager", "employee"])
def update_abnormal_remark():
    """员工更新异常备注/描述"""
    try:
        data = request.json
        abnormal_id = data.get('abnormal_id')
        remark = data.get('remark', '')

        if not abnormal_id:
            return api_response(400, "缺少异常记录ID")

        abn = AbnormalAttendance.query.get(abnormal_id)
        if not abn:
            return api_response(404, "异常记录不存在")

        # 权限校验：只能更新自己的记录
        current_emp_id = session.get('emp_id')
        if abn.emp_id != current_emp_id:
            return api_response(403, "无权修改他人的异常记录")

        # 状态校验：已处理的记录不允许修改备注
        if abn.is_processed == 1:
            return api_response(400, "记录已由管理人员处理，无法修改备注")

        # 更新备注并同步更新时间
        abn.abnormal_desc = remark
        abn.update_time = datetime.now()
        
        db.session.commit()
        return api_response(200, "备注更新成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"更新失败: {str(e)}")
