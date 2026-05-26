from datetime import datetime, date
from flask import Blueprint, request
from models import db, HolidayCalendar
from utils.decorators import api_role_required
from utils.api_helpers import api_response

holiday_bp = Blueprint('holiday_api', __name__)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, '%Y-%m-%d').date()


@holiday_bp.route('/holidays', methods=['GET'])
@api_role_required(["admin", "manager"])
def list_holidays():
    year = request.args.get('year')
    try:
        query = HolidayCalendar.query
        if year:
            y = int(year)
            start = date(y, 1, 1)
            end = date(y, 12, 31)
            query = query.filter(HolidayCalendar.holiday_date.between(start, end))
        items = query.order_by(HolidayCalendar.holiday_date.asc()).all()
    except Exception:
        return api_response(500, "节假日表未初始化，请先完成数据库迁移")
    data = [
        {
            "date": i.holiday_date.strftime('%Y-%m-%d'),
            "is_workday": int(i.is_workday or 0),
            "name": i.name or ""
        }
        for i in items
    ]
    return api_response(200, "查询成功", {"items": data})


@holiday_bp.route('/holidays', methods=['POST'])
@api_role_required(["admin", "manager"])
def upsert_holiday():
    payload = request.get_json(silent=True) or {}
    date_str = (payload.get('date') or '').strip()
    if not date_str:
        return api_response(400, "缺少日期")
    try:
        d = _parse_date(date_str)
    except Exception:
        return api_response(400, "日期格式错误，应为YYYY-MM-DD")

    try:
        is_workday = int(payload.get('is_workday'))
    except Exception:
        is_workday = 0
    is_workday = 1 if is_workday == 1 else 0

    name = (payload.get('name') or '').strip()

    try:
        rec = HolidayCalendar.query.get(d)
        if not rec:
            rec = HolidayCalendar(holiday_date=d)
            db.session.add(rec)

        rec.is_workday = is_workday
        rec.name = name
        db.session.commit()
    except Exception:
        db.session.rollback()
        return api_response(500, "保存失败：节假日表未初始化或数据库错误")
    return api_response(200, "保存成功")


@holiday_bp.route('/holidays/bulk', methods=['POST'])
@api_role_required(["admin", "manager"])
def bulk_upsert_holidays():
    payload = request.get_json(silent=True) or {}
    items = payload.get('items') or []
    if not isinstance(items, list) or not items:
        return api_response(400, "items为空")

    ok = 0
    try:
        for it in items:
            if not isinstance(it, dict):
                continue
            date_str = (it.get('date') or '').strip()
            if not date_str:
                continue
            try:
                d = _parse_date(date_str)
            except Exception:
                continue
            try:
                is_workday = int(it.get('is_workday'))
            except Exception:
                is_workday = 0
            is_workday = 1 if is_workday == 1 else 0
            name = (it.get('name') or '').strip()

            rec = HolidayCalendar.query.get(d)
            if not rec:
                rec = HolidayCalendar(holiday_date=d)
                db.session.add(rec)
            rec.is_workday = is_workday
            rec.name = name
            ok += 1

        db.session.commit()
    except Exception:
        db.session.rollback()
        return api_response(500, "导入失败：节假日表未初始化或数据库错误")
    return api_response(200, "导入成功", {"success": ok})


@holiday_bp.route('/holidays/<date_str>', methods=['DELETE'])
@api_role_required(["admin", "manager"])
def delete_holiday(date_str):
    try:
        d = _parse_date(date_str)
    except Exception:
        return api_response(400, "日期格式错误，应为YYYY-MM-DD")
    try:
        rec = HolidayCalendar.query.get(d)
        if not rec:
            return api_response(404, "记录不存在")
        db.session.delete(rec)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return api_response(500, "删除失败：节假日表未初始化或数据库错误")
    return api_response(200, "删除成功")
