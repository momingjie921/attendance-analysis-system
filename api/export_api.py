# api/export_api.py
from datetime import datetime, date, timedelta
import pandas as pd
from io import BytesIO
from flask import request, send_file, session
from sqlalchemy import and_, or_, func

from config.database import db
from models import Department, Employee, Attendance, AbnormalAttendance, User, AbnormalTypeEnum, SystemConfig
from utils.decorators import api_role_required
from .dashboard_api import get_month_range, api_response


@api_role_required(["admin", "manager"])
def export_data():
    # 获取导出参数
    export_type = request.args.get('type', 'attendance_trend')  # 导出类型
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year = request.args.get('year')
    quarter = request.args.get('quarter')
    dept_code = request.args.get('dept_code', '')  # 部门编码（部门维度导出用）
    emp_keyword = request.args.get('emp_keyword', '')  # 员工关键词（个人维度导出用）

    # 日期范围
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
        elif year:
            y = int(year)
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
        else:
            start_date, end_date = get_month_range(month)
    except Exception as e:
        return api_response(400, f"日期格式错误：{str(e)}")

    # 创建Excel内存流
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')

    try:
        # 导入模板下载
        if export_type == 'import_template':
            data = [{
                '姓名': '张三',
                '部门': '技术部',
                '上班打卡时间': '2025-01-01 08:55:00',
                '下班打卡时间': '2025-01-01 18:05:00',
                '异常标识': '0'
            }, {
                '姓名': '李四',
                '部门': '人事部',
                '上班打卡时间': '2025-01-01 09:00:00',
                '下班打卡时间': '2025-01-01 18:00:00',
                '异常标识': '2'
            }]
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name='考勤导入模板', index=False)
            worksheet = writer.sheets['考勤导入模板']
            for i, col in enumerate(df.columns):
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
                worksheet.column_dimensions[chr(65 + i)].width = column_len
            worksheet.cell(row=4, column=1, value="说明：异常标识列可选填，0=正常(默认)，1=旷工，2=请假")
            filename = "考勤数据导入模板.xlsx"
            
        # 全平台月度出勤率趋势导出
        elif export_type == 'attendance_trend':
            # 获取用户选择的导出年份，默认为当前年
            target_year = int(request.args.get('target_year', date.today().year))
            
            months = []
            rates = []
            # 导出全年的12个月
            for m in range(1, 13):
                calc_month_str = f"{target_year}-{m:02d}"
                calc_start, calc_end = get_month_range(calc_month_str)

                # 计算出勤率
                active_emps = Employee.query.filter_by(status=1).all()
                active_emp_ids = [e.emp_id for e in active_emps]
                active_emp_count = len(active_emp_ids)
                
                # 获取该月的工作日天数
                from utils.api_helpers import get_working_days
                month_days = get_working_days(calc_start, calc_end)
                
                rate = 0.0
                if active_emp_count > 0 and month_days > 0:
                    att_count = Attendance.query.filter(
                        Attendance.emp_id.in_(active_emp_ids),
                        Attendance.att_date.between(calc_start, calc_end),
                        Attendance.is_absent == 0
                    ).count()
                    rate = round(att_count / (active_emp_count * month_days) * 100, 1)

                months.append(calc_month_str)
                rates.append(rate)

            # 写入Excel
            df = pd.DataFrame({
                '月份': months,
                '出勤率(%)': rates
            })
            df.to_excel(writer, sheet_name='全平台出勤率趋势', index=False)
            filename = f"全平台月度出勤率趋势_{target_year}年.xlsx"

        # 2. 部门异常分布导出
        elif export_type == 'dept_abnormal':
            # 获取导出年份，默认为当前年
            target_year = int(request.args.get('target_year', date.today().year))
            
            # 统一使用 dashboard_api 中的过滤条件
            sys_config = {c.config_key: c.config_value for c in SystemConfig.query.all()}
            late_threshold = int(float(sys_config.get('lateThreshold') or 0))
            early_threshold = int(float(sys_config.get('earlyLeaveThreshold') or 0))

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

            # 获取全年的起止日期
            year_start = date(target_year, 1, 1)
            year_end = date(target_year, 12, 31)

            depts = Department.query.filter_by(status=1).all()
            dept_names = []
            abnormal_counts = []
            for dept in depts:
                dept_emp_ids = [emp.emp_id for emp in dept.employees if emp.status == 1]
                if not dept_emp_ids:
                    dept_names.append(dept.dept_name)
                    abnormal_counts.append(0)
                    continue

                abn_count = AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id.in_(dept_emp_ids),
                    AbnormalAttendance.abnormal_date.between(year_start, year_end)
                ).outerjoin(Attendance, 
                    (AbnormalAttendance.emp_id == Attendance.emp_id) & 
                    (AbnormalAttendance.abnormal_date == Attendance.att_date)
                ).filter(abnormal_cond).count()
                
                dept_names.append(dept.dept_name)
                abnormal_counts.append(abn_count)

            df = pd.DataFrame({
                '部门名称': dept_names,
                '异常次数': abnormal_counts
            })
            df.to_excel(writer, sheet_name='部门异常分布', index=False)
            filename = f"部门异常分布_{target_year}年.xlsx"

        # 2.1 部门月度出勤率趋势导出
        elif export_type == 'dept_attendance_trend':
            if not dept_code:
                return api_response(400, "请指定部门编码")
            dept = Department.query.filter_by(dept_code=dept_code, status=1).first()
            if not dept:
                return api_response(404, "部门不存在")

            dept_emp_ids = [emp.emp_id for emp in dept.employees if emp.status == 1]
            dept_emp_count = len(dept_emp_ids)

            def get_dept_month_counts(start_d: date, end_d: date):
                if not dept_emp_ids:
                    return {}
                results = db.session.query(
                    func.date_format(Attendance.att_date, '%Y-%m').label('month'),
                    func.count(Attendance.att_id).label('count')
                ).filter(
                    Attendance.emp_id.in_(dept_emp_ids),
                    Attendance.att_date.between(start_d, end_d),
                    Attendance.is_absent == 0
                ).group_by(func.date_format(Attendance.att_date, '%Y-%m')).all()
                return {r.month: r.count for r in results}

            def month_days_of(m_start: date, m_end: date) -> int:
                return (m_end - m_start).days + 1

            months = []
            rates = []
            if year or (quarter and year):
                selected_year = int(year) if year else start_date.year
                data = get_dept_month_counts(date(selected_year, 1, 1), date(selected_year, 12, 31))
                for m in range(1, 13):
                    month_str = f"{selected_year}-{m:02d}"
                    m_start = date(selected_year, m, 1)
                    next_m = date(selected_year + 1, 1, 1) if m == 12 else date(selected_year, m + 1, 1)
                    m_end = next_m - timedelta(days=1)
                    mdays = month_days_of(m_start, m_end)
                    rate = 0.0
                    if dept_emp_count > 0 and mdays > 0:
                        rate = round(data.get(month_str, 0) / (dept_emp_count * mdays) * 100, 1)
                    months.append(month_str)
                    rates.append(rate)
                filename = f"{dept.dept_name}_月度出勤率趋势_{selected_year}年.xlsx"
            else:
                current_year, current_month = map(int, month.split('-'))
                trend_start_year = current_year
                trend_start_month = current_month - 11
                if trend_start_month <= 0:
                    trend_start_month += 12
                    trend_start_year -= 1
                trend_start_date = date(trend_start_year, trend_start_month, 1)
                data = get_dept_month_counts(trend_start_date, end_date)
                for i in range(11, -1, -1):
                    m = current_month - i
                    y = current_year
                    if m <= 0:
                        m += 12
                        y -= 1
                    month_str = f"{y}-{m:02d}"
                    m_start, m_end = get_month_range(month_str)
                    mdays = month_days_of(m_start, m_end)
                    rate = 0.0
                    if dept_emp_count > 0 and mdays > 0:
                        rate = round(data.get(month_str, 0) / (dept_emp_count * mdays) * 100, 1)
                    months.append(month_str)
                    rates.append(rate)
                filename = f"{dept.dept_name}_月度出勤率趋势_{month}_近12个月.xlsx"

            df = pd.DataFrame({'月份': months, '出勤率(%)': rates})
            df.to_excel(writer, sheet_name='部门出勤率趋势', index=False)

        # 2.2 部门异常类型分布导出
        elif export_type == 'dept_abnormal_type':
            if not dept_code:
                return api_response(400, "请指定部门编码")
            dept = Department.query.filter_by(dept_code=dept_code, status=1).first()
            if not dept:
                return api_response(404, "部门不存在")

            dept_emp_ids = [emp.emp_id for emp in dept.employees if emp.status == 1]

            sys_config = {c.config_key: c.config_value for c in SystemConfig.query.all()}
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

            from utils.api_helpers import ABNORMAL_TYPE_CN

            rows = []
            if dept_emp_ids:
                rows = (
                    db.session.query(
                        AbnormalAttendance.abnormal_type.label('type'),
                        func.count(AbnormalAttendance.abnormal_id).label('count')
                    ).filter(
                        AbnormalAttendance.emp_id.in_(dept_emp_ids),
                        AbnormalAttendance.abnormal_date.between(start_date, end_date),
                    ).outerjoin(
                        Attendance,
                        (AbnormalAttendance.emp_id == Attendance.emp_id) & (AbnormalAttendance.abnormal_date == Attendance.att_date)
                    ).filter(abnormal_cond).group_by(AbnormalAttendance.abnormal_type).all()
                )

            data = []
            for abn_type, cnt in rows:
                key = abn_type.value if hasattr(abn_type, 'value') else str(abn_type)
                data.append({'异常类型': ABNORMAL_TYPE_CN.get(key, key), '异常次数': int(cnt)})

            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name='部门异常类型分布', index=False)

            if year:
                filename = f"{dept.dept_name}_异常类型分布_{year}年.xlsx"
            elif quarter and year:
                filename = f"{dept.dept_name}_异常类型分布_{year}_{quarter}.xlsx"
            else:
                filename = f"{dept.dept_name}_异常类型分布_{month}.xlsx"

        # 3. 部门员工排名导出
        elif export_type == 'dept_employee_rank':
            if not dept_code:
                return api_response(400, "请指定部门编码")
            dept = Department.query.filter_by(dept_code=dept_code, status=1).first()
            if not dept:
                return api_response(404, "部门不存在")

            # 部门员工出勤率数据
            emp_data = []
            for emp in dept.employees.filter_by(status=1):
                att_days = Attendance.query.filter(
                    Attendance.emp_id == emp.emp_id,
                    Attendance.att_date.between(start_date, end_date),
                    Attendance.is_absent == 0
                ).count()
                month_days = (end_date - start_date).days + 1
                att_rate = round(att_days / month_days * 100, 1) if month_days else 0.0
                abn_count = AbnormalAttendance.query.filter(
                    AbnormalAttendance.emp_id == emp.emp_id,
                    AbnormalAttendance.abnormal_date.between(start_date, end_date)
                ).count()
                late_total = Attendance.query.filter(
                    Attendance.emp_id == emp.emp_id,
                    Attendance.att_date.between(start_date, end_date)
                ).with_entities(pd.func.sum(Attendance.late_minutes)).scalar() or 0

                emp_data.append({
                    '员工姓名': emp.emp_name,
                    '员工工号': emp.emp_code,
                    '本月出勤天数': att_days,
                    '出勤率(%)': att_rate,
                    '异常次数': abn_count,
                    '累计迟到时长(分钟)': late_total
                })

            # 排序
            df = pd.DataFrame(emp_data)
            df = df.sort_values('出勤率(%)', ascending=False)
            df.insert(0, '排名', range(1, len(df) + 1))  # 添加排名列
            df.to_excel(writer, sheet_name=f'{dept.dept_name}员工排名', index=False)
            filename = f"{dept.dept_name}员工出勤率排名_{month}.xlsx"

        # 3.1 个人打卡趋势导出
        elif export_type == 'personal_checkin':
            # 获取员工
            if session.get('role') == 'employee':
                emp = Employee.query.filter_by(emp_id=session.get('emp_id'), status=1).first()
            else:
                if not emp_keyword:
                    return api_response(400, "请输入员工姓名/工号")
                emp = Employee.query.filter(
                    (Employee.emp_name.like(f"%{emp_keyword}%")) | (Employee.emp_code.like(f"%{emp_keyword}%")),
                    Employee.status == 1
                ).first()

            if not emp:
                return api_response(404, "员工不存在")

            def to_hour_decimal(dt_value):
                if not dt_value:
                    return None
                return round(dt_value.hour + dt_value.minute / 60, 1)

            def to_hhmm(hour_decimal):
                if hour_decimal is None:
                    return ''
                hours = int(hour_decimal)
                minutes = int(round((hour_decimal - hours) * 60))
                if minutes == 60:
                    hours += 1
                    minutes = 0
                return f"{hours:02d}:{minutes:02d}"

            rows = []
            if year:
                y = int(year)
                for m in range(1, 13):
                    m_start = date(y, m, 1)
                    next_m = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
                    m_end = next_m - timedelta(days=1)
                    attendances = Attendance.query.filter(
                        Attendance.emp_id == emp.emp_id,
                        Attendance.att_date.between(m_start, m_end),
                        Attendance.is_absent == 0
                    ).all()

                    if not attendances:
                        rows.append({
                            '月份': f"{y}-{m:02d}",
                            '平均上班打卡': '',
                            '平均下班打卡': ''
                        })
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

                    rows.append({
                        '月份': f"{y}-{m:02d}",
                        '平均上班打卡': to_hhmm(avg_in),
                        '平均下班打卡': to_hhmm(avg_out)
                    })

                filename = f"{emp.emp_name}_打卡趋势_{y}年.xlsx"

            elif quarter and year:
                y = int(year)
                q = quarter.upper()
                if q == 'Q1':
                    months_range = [1, 2, 3]
                elif q == 'Q2':
                    months_range = [4, 5, 6]
                elif q == 'Q3':
                    months_range = [7, 8, 9]
                elif q == 'Q4':
                    months_range = [10, 11, 12]
                else:
                    return api_response(400, f"季度格式错误：{quarter}")

                for m in months_range:
                    m_start = date(y, m, 1)
                    next_m = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
                    m_end = next_m - timedelta(days=1)
                    attendances = Attendance.query.filter(
                        Attendance.emp_id == emp.emp_id,
                        Attendance.att_date.between(m_start, m_end),
                        Attendance.is_absent == 0
                    ).all()

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

                    rows.append({
                        '月份': f"{y}-{m:02d}",
                        '平均上班打卡': to_hhmm(avg_in),
                        '平均下班打卡': to_hhmm(avg_out)
                    })

                filename = f"{emp.emp_name}_打卡趋势_{y}_{q}.xlsx"

            else:
                # 月度：导出每日打卡明细
                curr = start_date
                while curr <= end_date:
                    att = Attendance.query.filter_by(emp_id=emp.emp_id, att_date=curr).first()
                    in_h = to_hour_decimal(att.check_in_time) if att else None
                    out_h = to_hour_decimal(att.check_out_time) if att else None
                    rows.append({
                        '日期': curr.strftime('%Y-%m-%d'),
                        '上班打卡': to_hhmm(in_h),
                        '下班打卡': to_hhmm(out_h)
                    })
                    curr += timedelta(days=1)

                filename = f"{emp.emp_name}_打卡明细_{month}.xlsx"

            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name='打卡趋势', index=False)

        # 4. 个人异常明细导出
        elif export_type == 'personal_abnormal':
            # 获取员工
            if session.get('role') == 'employee':
                emp = Employee.query.filter_by(emp_id=session.get('emp_id'), status=1).first()
            else:
                if not emp_keyword:
                    return api_response(400, "请输入员工姓名/工号")
                emp = Employee.query.filter(
                    (Employee.emp_name.like(f"%{emp_keyword}%")) | (Employee.emp_code.like(f"%{emp_keyword}%")),
                    Employee.status == 1
                ).first()

            if not emp:
                return api_response(404, "员工不存在")

            # 个人异常明细
            abn_detail = AbnormalAttendance.query.filter(
                AbnormalAttendance.emp_id == emp.emp_id,
                AbnormalAttendance.abnormal_date.between(start_date, end_date)
            ).join(Attendance,
                   (AbnormalAttendance.emp_id == Attendance.emp_id) &
                   (AbnormalAttendance.abnormal_date == Attendance.att_date)
                   ).with_entities(
                AbnormalAttendance.abnormal_date,
                AbnormalAttendance.abnormal_type,
                Attendance.check_in_time,
                Attendance.check_out_time,
                Attendance.late_minutes,
                Attendance.early_minutes,
                AbnormalAttendance.abnormal_desc,
                AbnormalAttendance.is_processed
            ).all()

            # 格式化数据
            from utils.api_helpers import ABNORMAL_TYPE_CN
            data = []
            for rec in abn_detail:
                abn_date, abn_type, check_in, check_out, late, early, remark, processed = rec
                data.append({
                    '异常日期': abn_date.strftime('%Y-%m-%d'),
                    '异常类型': ABNORMAL_TYPE_CN.get(abn_type.value, abn_type.value),
                    '上班打卡时间': check_in.strftime('%H:%M:%S') if check_in else '-',
                    '下班打卡时间': check_out.strftime('%H:%M:%S') if check_out else '-',
                    '迟到时长(分钟)': late,
                    '早退时长(分钟)': early,
                    '备注': remark or '-',
                    '处理状态': '已处理' if processed == 1 else '待处理'
                })

            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=f'{emp.emp_name}异常明细', index=False)
            filename = f"{emp.emp_name}异常考勤明细_{month}.xlsx"

            # 5. 员工数据导出
        elif export_type == 'employee_export':
            # 构建查询
            query = Employee.query
            query = query.join(Department, Employee.dept_id == Department.dept_id)

            # 搜索条件
            emp_keyword = request.args.get('emp_keyword', '')
            if emp_keyword:
                query = query.filter(
                    db.or_(
                        Employee.emp_name.like(f"%{emp_keyword}%"),
                        Employee.emp_code.like(f"%{emp_keyword}%"),
                        Employee.phone.like(f"%{emp_keyword}%"),
                        Employee.email.like(f"%{emp_keyword}%")
                    )
                )

            # 部门筛选
            dept_id = request.args.get('dept_id')
            if dept_id:
                query = query.filter(Employee.dept_id == dept_id)

            # 状态筛选
            status = request.args.get('status')
            if status:
                query = query.filter(Employee.status == int(status))

            employees = query.all()

            # 格式化数据
            data = []
            for emp in employees:
                user = User.query.filter_by(emp_id=emp.emp_id).first()
                data.append({
                    '员工编号': emp.emp_code,
                    '员工姓名': emp.emp_name,
                    '所属部门': emp.department.dept_name if emp.department else '',
                    '手机号': emp.phone or '',
                    '邮箱': emp.email or '',
                    '入职时间': emp.entry_time.strftime('%Y-%m-%d') if emp.entry_time else '',
                    '状态': '在职' if emp.status == 1 else '离职',
                    '登录账号': user.username if user else '',
                    '用户角色': user.role if user else '',
                    '账户状态': '已启用' if user and user.status == 1 else '未启用'
                })

            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name='员工数据', index=False)
            filename = f"员工数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        else:
            return api_response(400, "不支持的导出类型")

        # 保存Excel并重置流指针
        writer.close()
        output.seek(0)

        # 返回文件
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return api_response(500, f"导出失败：{str(e)}")
