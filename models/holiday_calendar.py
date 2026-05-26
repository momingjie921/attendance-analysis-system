from datetime import datetime
from models import db
from sqlalchemy.dialects.mysql import DATE


class HolidayCalendar(db.Model):
    __tablename__ = 'holiday_calendar'

    holiday_date = db.Column(DATE, primary_key=True, comment='日期')
    is_workday = db.Column(db.SmallInteger, default=0, nullable=False, comment='是否工作日：1-工作日 0-节假日/休息日')
    name = db.Column(db.String(50), nullable=True, comment='名称')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f"<HolidayCalendar {self.holiday_date} {self.is_workday}>"
