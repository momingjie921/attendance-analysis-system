from typing import Dict, Any, Optional, Tuple
from datetime import date, timedelta
from flask import jsonify

# 异常类型中英文映射
ABNORMAL_TYPE_CN = {
    'LATE': '迟到',
    'EARLY': '早退',
    'ABSENT': '旷工',
    'MISSING_CHECK': '漏打卡'
}

def api_response(code: int = 200, msg: str = "成功", data: Optional[Dict[str, Any]] = None) -> Any:
    """统一API响应格式"""
    return jsonify({
        "code": code,
        "msg": msg,
        "data": data if data is not None else {}
    }), code

def get_month_range(month_str: str) -> Tuple[date, date]:
    """获取月份的开始/结束日期"""
    year, month = map(int, month_str.split('-'))
    start_date = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    end_date = next_month - timedelta(days=1)
    return start_date, end_date


def _get_holiday_check_rule():
    """读取系统配置中的节假日检查规则，默认返回 0"""
    try:
        from models import SystemConfig
        config = SystemConfig.query.filter_by(config_key='holidayCheckRule').first()
        return int(float(config.config_value)) if config else 0
    except Exception:
        return 0


def get_working_days(start_date: date, end_date: date, holiday_check_rule: int = None) -> int:
    if holiday_check_rule is None:
        holiday_check_rule = _get_holiday_check_rule()

    # rule 2: all days are workdays
    if holiday_check_rule == 2:
        return (end_date - start_date).days + 1

    days = 0
    current_date = start_date
    calendar_map = {}
    try:
        from models import HolidayCalendar
        recs = HolidayCalendar.query.filter(
            HolidayCalendar.holiday_date.between(start_date, end_date)
        ).all()
        calendar_map = {r.holiday_date: int(r.is_workday or 0) for r in recs}
    except Exception:
        calendar_map = {}

    while current_date <= end_date:
        if current_date in calendar_map:
            if calendar_map[current_date] == 1:
                days += 1
        else:
            if current_date.weekday() < 5:
                days += 1
        current_date += timedelta(days=1)
    return days


def get_working_dates(start_date: date, end_date: date, holiday_check_rule: int = None):
    if holiday_check_rule is None:
        holiday_check_rule = _get_holiday_check_rule()

    # rule 2: all days are workdays
    if holiday_check_rule == 2:
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date)
            current_date += timedelta(days=1)
        return dates

    current_date = start_date
    calendar_map = {}
    try:
        from models import HolidayCalendar
        recs = HolidayCalendar.query.filter(
            HolidayCalendar.holiday_date.between(start_date, end_date)
        ).all()
        calendar_map = {r.holiday_date: int(r.is_workday or 0) for r in recs}
    except Exception:
        calendar_map = {}

    dates = []
    while current_date <= end_date:
        is_working = False
        if current_date in calendar_map:
            is_working = calendar_map[current_date] == 1
        else:
            is_working = current_date.weekday() < 5
        if is_working:
            dates.append(current_date)
        current_date += timedelta(days=1)
    return dates
