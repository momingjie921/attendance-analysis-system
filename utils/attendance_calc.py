from datetime import datetime, date, timedelta
from models import db, Attendance, AbnormalAttendance, AbnormalTypeEnum, Leave, HolidayCalendar

def calculate_attendance_status(att_record: Attendance, sys_config: dict, manual_flag: int = None):
    """
    根据系统配置计算单条考勤记录的状态（迟到、早退、旷工等）
    manual_flag: 来自导入文件的手动标识 (1=旷工, 2=迟到/早退)
    """
    att_date = att_record.att_date
    
    # 假期规则检查
    # 0: 法定节假日自动跳过
    # 1: 固定双休跳过
    # 2: 全考勤
    holiday_rule = int(sys_config.get('holidayCheckRule', 0))
    is_weekend = att_date.weekday() >= 5

    holiday_cache = sys_config.setdefault('_holiday_cache', {})
    k = att_date.isoformat()
    cal_is_workday = None
    if holiday_rule == 0:
        if k in holiday_cache:
            cal_is_workday = holiday_cache.get(k)
        else:
            try:
                rec = HolidayCalendar.query.get(att_date)
                cal_is_workday = int(rec.is_workday) if rec else None
            except Exception:
                cal_is_workday = None
            holiday_cache[k] = cal_is_workday

        if cal_is_workday == 0 or (cal_is_workday is None and is_weekend):
            att_record.late_minutes = 0
            att_record.early_minutes = 0
            att_record.is_absent = 0
            AbnormalAttendance.query.filter_by(emp_id=att_record.emp_id, abnormal_date=att_date).delete()
            return att_record

    # 时间配置解析
    work_start_str = sys_config.get('workStartTime', '09:00')
    work_end_str = sys_config.get('workEndTime', '18:00')
    
    # 处理时间格式 (HH:mm 或 HH:mm:ss)
    if len(work_start_str) == 5: work_start_str += ':00'
    if len(work_end_str) == 5: work_end_str += ':00'
    
    work_start_time = datetime.strptime(work_start_str, '%H:%M:%S').time()
    work_end_time = datetime.strptime(work_end_str, '%H:%M:%S').time()
    
    absent_threshold_hours = float(sys_config.get('absentThreshold', 4))
    late_threshold = int(float(sys_config.get('lateThreshold', 0)))
    early_threshold = int(float(sys_config.get('earlyLeaveThreshold', 0)))

    # 基于配置计算迟到早退
    start_work = datetime.combine(att_date, work_start_time)
    end_work = datetime.combine(att_date, work_end_time)
    day_work_minutes = int((end_work - start_work).total_seconds() / 60) if end_work > start_work else 0

    leave_minutes = 0
    leave_days_for_date = 0.0
    leave_half_hint = None
    leave_cache = sys_config.setdefault('_leave_cache', {})
    leave_key = (int(att_record.emp_id), k)
    if leave_key in leave_cache:
        cached = leave_cache.get(leave_key)
        if isinstance(cached, dict):
            leave_days_for_date = float(cached.get('days') or 0.0)
            leave_half_hint = cached.get('half') or None
        else:
            leave_days_for_date = float(cached or 0.0)
    else:
        try:
            leaves = Leave.query.filter(
                Leave.emp_id == att_record.emp_id,
                Leave.approval_status == 'approved',
                Leave.start_date <= att_date,
                Leave.end_date >= att_date
            ).all()
        except Exception:
            leaves = []

        for lv in leaves:
            span = (lv.end_date - lv.start_date).days + 1
            if span <= 0:
                continue
            try:
                days = float(lv.leave_days)
            except Exception:
                continue
            if days <= 0:
                continue
            if span == 1 and days == 0.5:
                v = getattr(lv, 'leave_half_day', None)
                if v in ('AM', 'PM'):
                    leave_half_hint = v
            per_day = days / span
            leave_days_for_date += per_day

        if leave_days_for_date > 1:
            leave_days_for_date = 1.0
        leave_cache[leave_key] = {'days': float(leave_days_for_date), 'half': leave_half_hint}

    if day_work_minutes > 0 and leave_days_for_date > 0:
        leave_minutes = int(round(day_work_minutes * leave_days_for_date))

    if day_work_minutes > 0 and leave_days_for_date >= 1:
        att_record.late_minutes = 0
        att_record.early_minutes = 0
        att_record.is_absent = 0
        AbnormalAttendance.query.filter_by(emp_id=att_record.emp_id, abnormal_date=att_date).delete()
        return att_record

    missing_in = not bool(att_record.check_in_time)
    missing_out = not bool(att_record.check_out_time)
    mid_work = start_work + timedelta(minutes=day_work_minutes / 2) if day_work_minutes > 0 else start_work
    leave_half = leave_half_hint
    if leave_half is None and day_work_minutes > 0 and 0.5 <= leave_days_for_date < 1:
        if missing_in and not missing_out:
            leave_half = 'AM'
        elif missing_out and not missing_in:
            leave_half = 'PM'
        elif not missing_in and not missing_out:
            if att_record.check_in_time and att_record.check_in_time >= mid_work:
                leave_half = 'AM'
            elif att_record.check_out_time and att_record.check_out_time <= mid_work:
                leave_half = 'PM'

    expected_start = mid_work if leave_half == 'AM' else start_work
    expected_end = mid_work if leave_half == 'PM' else end_work
    
    # 1. 迟到判定
    if att_record.check_in_time and att_record.check_in_time > expected_start:
        diff = (att_record.check_in_time - expected_start).total_seconds() / 60
        # 如果手动标记为2，只要有差值就记录；否则按阈值
        if manual_flag == 2 or diff > late_threshold:
            att_record.late_minutes = int(diff)
        else:
            att_record.late_minutes = 0
    else:
        att_record.late_minutes = 0
        
    # 2. 早退判定
    if att_record.check_out_time and att_record.check_out_time < expected_end:
        diff = (expected_end - att_record.check_out_time).total_seconds() / 60
        # 如果手动标记为2，只要有差值就记录；否则按阈值
        if manual_flag == 2 or diff > early_threshold:
            att_record.early_minutes = int(diff)
        else:
            att_record.early_minutes = 0
    else:
        att_record.early_minutes = 0

    # 3. 计算工时及自动旷工判定
    threshold_minutes = int(absent_threshold_hours * 60)
    
    # 逻辑：如果手动标记为 1 (旷工)，则直接判定为旷工
    if manual_flag == 1:
        att_record.work_duration = 0
        att_record.is_absent = 1
    elif att_record.check_in_time and att_record.check_out_time:
        duration = (att_record.check_out_time - att_record.check_in_time).total_seconds() / 60
        work_minutes = int(duration) if duration > 0 else 0
        att_record.work_duration = work_minutes
        effective = work_minutes + leave_minutes
        att_record.is_absent = 1 if effective < threshold_minutes else 0
    elif missing_in and missing_out:
        att_record.work_duration = 0
        effective = 0 + leave_minutes
        att_record.is_absent = 1 if effective < threshold_minutes else 0
    else:
        att_record.work_duration = 0
        att_record.is_absent = 0

    # 4. 更新异常记录 (AbnormalAttendance)
    # 先清除当天的旧异常记录
    AbnormalAttendance.query.filter_by(emp_id=att_record.emp_id, abnormal_date=att_date).delete()
    
    new_abnormals = []
    
    # 旷工
    if att_record.is_absent == 1:
        new_abnormals.append(AbnormalAttendance(
            emp_id=att_record.emp_id,
            abnormal_date=att_date,
            abnormal_type=AbnormalTypeEnum.ABSENT,
            abnormal_desc="工时不足或标记旷工"
        ))
    
    # 迟到
    if att_record.late_minutes > 0:
        new_abnormals.append(AbnormalAttendance(
            emp_id=att_record.emp_id,
            abnormal_date=att_date,
            abnormal_type=AbnormalTypeEnum.LATE,
            abnormal_desc=f"迟到 {att_record.late_minutes} 分钟"
        ))
        
    # 早退
    if att_record.early_minutes > 0:
        new_abnormals.append(AbnormalAttendance(
            emp_id=att_record.emp_id,
            abnormal_date=att_date,
            abnormal_type=AbnormalTypeEnum.EARLY,
            abnormal_desc=f"早退 {att_record.early_minutes} 分钟"
        ))
        
    if att_record.is_absent == 0:
        if missing_in or missing_out:
            waive = False
            if leave_half == 'AM' and missing_in and not missing_out:
                waive = True
            elif leave_half == 'PM' and missing_out and not missing_in:
                waive = True
            if not waive:
                desc = []
                if missing_in:
                    desc.append("缺上班卡")
                if missing_out:
                    desc.append("缺下班卡")
                new_abnormals.append(AbnormalAttendance(
                    emp_id=att_record.emp_id,
                    abnormal_date=att_date,
                    abnormal_type=AbnormalTypeEnum.MISSING_CHECK,
                    abnormal_desc=",".join(desc)
                ))

    for abn in new_abnormals:
        db.session.add(abn)
    
    return att_record
