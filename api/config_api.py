from flask import Blueprint, jsonify, request
from models import db, SystemConfig, Attendance
from datetime import datetime
from utils.attendance_calc import calculate_attendance_status
from utils.api_helpers import get_month_range

config_bp = Blueprint('config_api', __name__)

# 默认配置
DEFAULT_CONFIG = {
    'workStartTime': '09:00',
    'workEndTime': '18:00',
    'lateThreshold': '15',
    'earlyLeaveThreshold': '15',
    'absentThreshold': '4',
    'checkInValidTime': '8',
    'lateMaxCount': '3',
    'absentMaxCount': '1',
    'exceptionReviewTime': '24',
    'holidayCheckRule': '0',
    'annualLeaveDays': '10',
    'sickLeaveDays': '1',
    'leaveApplyNotice': '4'
}

@config_bp.route('/config/rules', methods=['GET'])
def get_config():
    """获取系统配置"""
    try:
        configs = SystemConfig.query.all()
        config_dict = {c.config_key: c.config_value for c in configs}
        
        # 合并默认配置（如果数据库中没有，使用默认值）
        result = DEFAULT_CONFIG.copy()
        result.update(config_dict)
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': result
        })
    except Exception as e:
        return jsonify({'code': 500, 'msg': str(e)}), 500

@config_bp.route('/config/recalculate', methods=['POST'])
def recalculate_attendance():
    """根据当前规则重新计算考勤历史数据"""
    try:
        data = request.json
        month = data.get('month')
        if not month:
            return jsonify({'code': 400, 'msg': '请选择月份'}), 400

        # 获取当前系统配置
        configs = SystemConfig.query.all()
        sys_config = DEFAULT_CONFIG.copy()
        sys_config.update({c.config_key: c.config_value for c in configs})

        # 获取月份范围
        start_date, end_date = get_month_range(month)

        # 查询该月的所有考勤记录
        attendance_records = Attendance.query.filter(
            Attendance.att_date.between(start_date, end_date)
        ).all()

        if not attendance_records:
            return jsonify({'code': 200, 'msg': f'{month} 月份没有可计算的考勤记录'})

        # 逐条计算并更新
        for record in attendance_records:
            calculate_attendance_status(record, sys_config)

        db.session.commit()
        return jsonify({'code': 200, 'msg': f'已完成 {len(attendance_records)} 条记录的重新计算'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': str(e)}), 500

@config_bp.route('/config/rules', methods=['POST'])
def update_config():
    """更新系统配置"""
    try:
        data = request.json
        if not data:
            return jsonify({'code': 400, 'msg': '无数据提交'}), 400

        # 遍历提交的数据并更新
        for key, value in data.items():
            if key in DEFAULT_CONFIG:
                config = SystemConfig.query.filter_by(config_key=key).first()
                if config:
                    config.config_value = str(value)
                    config.update_time = datetime.now()
                else:
                    # 判断类型
                    config_type = 'string'
                    if key in ['lateThreshold', 'earlyLeaveThreshold', 'absentThreshold', 'checkInValidTime', 
                               'lateMaxCount', 'absentMaxCount', 'exceptionReviewTime', 
                               'annualLeaveDays', 'sickLeaveDays', 'leaveApplyNotice']:
                        config_type = 'number'
                    elif key in ['workStartTime', 'workEndTime']:
                        config_type = 'time'
                        
                    new_config = SystemConfig(
                        config_key=key,
                        config_value=str(value),
                        config_type=config_type,
                        config_desc=get_config_desc(key)
                    )
                    db.session.add(new_config)
        
        db.session.commit()
        return jsonify({'code': 200, 'msg': '配置保存成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': str(e)}), 500

def get_config_desc(key):
    """获取配置项描述"""
    descs = {
        'workStartTime': '上班打卡时间',
        'workEndTime': '下班打卡时间',
        'lateThreshold': '迟到阈值（分钟）',
        'earlyLeaveThreshold': '早退阈值（分钟）',
        'absentThreshold': '旷工判定时长（小时）',
        'checkInValidTime': '打卡有效时长（小时）',
        'lateMaxCount': '月度迟到最大次数',
        'absentMaxCount': '月度旷工最大次数',
        'exceptionReviewTime': '异常审核时效（小时）',
        'holidayCheckRule': '节假日打卡规则',
        'annualLeaveDays': '年度带薪年假（天）',
        'sickLeaveDays': '月度带薪病假（天）',
        'leaveApplyNotice': '请假提前通知时长（小时）'
    }
    return descs.get(key, '系统配置')
