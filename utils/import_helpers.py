"""考勤数据导入的公共工具函数，供 import_api.py 和 manager_api.py 共用"""
import pandas as pd
from datetime import datetime
from models import SystemConfig


def get_system_config():
    defaults = {
        'workStartTime': '09:00',
        'workEndTime': '18:00',
        'absentThreshold': '4'
    }
    try:
        configs = SystemConfig.query.all()
        config_dict = {c.config_key: c.config_value for c in configs}
        for k, v in defaults.items():
            if k not in config_dict:
                config_dict[k] = v
        return config_dict
    except Exception:
        return defaults


def find_best_match(columns, target_key, candidates, current_map_val):
    if current_map_val and current_map_val in columns:
        return current_map_val

    for cand in candidates:
        if cand in columns:
            return cand

    keywords = []
    exclude = []

    if target_key == 'name':
        keywords = ['姓名', 'Name', 'User', 'Employee', '人员']
    elif target_key == 'dept':
        keywords = ['部门', 'Dept', 'Department', '科室']
    elif target_key == 'check_in':
        keywords = ['上班', '签到', 'CheckIn', 'Start', 'InTime', 'In']
        exclude = ['下班', '签退', 'CheckOut', 'End', 'OutTime', 'Out']
    elif target_key == 'check_out':
        keywords = ['下班', '签退', 'CheckOut', 'End', 'OutTime', 'Out']
        exclude = ['上班', '签到', 'CheckIn', 'Start', 'InTime', 'In']

    if keywords:
        for col in columns:
            col_str = str(col)
            if any(k in col_str for k in keywords):
                if not any(e in col_str for e in exclude):
                    return col

    return current_map_val or ''


def read_uploaded_file(file):
    """读取上传文件为 DataFrame"""
    if file.filename.endswith('.csv'):
        return pd.read_csv(file)
    elif file.filename.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file)
    else:
        raise ValueError('不支持的文件格式')


def read_uploaded_file_headers(file):
    """读取上传文件的列表头"""
    if file.filename.endswith('.csv'):
        df = pd.read_csv(file, nrows=0)
    elif file.filename.endswith(('.xls', '.xlsx')):
        df = pd.read_excel(file, nrows=0)
    else:
        raise ValueError('不支持的文件格式')
    return df.columns.tolist()


def get_column_mapping(columns, map_name=None, map_dept=None, map_check_in=None,
                       map_check_out=None, map_abnormal_flag=None):
    """计算列映射，如果缺失则抛出异常"""
    mapping = {
        'name': find_best_match(columns, 'name', ['姓名', '员工姓名', 'User', 'Name', 'UserName'], map_name),
        'dept': find_best_match(columns, 'dept', ['部门', '所属部门', 'Dept', 'Department'], map_dept),
        'check_in': find_best_match(columns, 'check_in', ['上班打卡时间', '上班打卡', '签到时间', '签到', 'CheckIn', 'StartTime'], map_check_in),
        'check_out': find_best_match(columns, 'check_out', ['下班打卡时间', '下班打卡', '签退时间', '签退', 'CheckOut', 'EndTime'], map_check_out),
        'abnormal_flag': find_best_match(columns, 'abnormal_flag', ['异常标识', '状态', 'Status', 'Flag'], map_abnormal_flag),
    }

    missing = []
    if mapping['name'] not in columns:
        missing.append(f"姓名列 '{mapping['name']}'")
    if mapping['dept'] not in columns:
        missing.append(f"部门列 '{mapping['dept']}'")
    if mapping['check_in'] not in columns:
        missing.append(f"上班打卡时间列 '{mapping['check_in']}'")
    if mapping['check_out'] not in columns:
        missing.append(f"下班打卡时间列 '{mapping['check_out']}'")

    if missing:
        raise ValueError(f"文件缺少以下必要列: {', '.join(missing)}")

    return mapping


def parse_attendance_row(row, mapping):
    """解析考勤行数据，返回 (emp_name, dept_name, check_in_dt, check_out_dt, flag_val, error)"""
    raw_name = row.get(mapping['name'])
    raw_dept = row.get(mapping['dept'])
    raw_in = row.get(mapping['check_in'])
    raw_out = row.get(mapping['check_out'])
    raw_flag = row.get(mapping['abnormal_flag']) if mapping['abnormal_flag'] in row.index else 0

    emp_name = str(raw_name).strip() if pd.notna(raw_name) else ""
    dept_name = str(raw_dept).strip() if pd.notna(raw_dept) else ""

    if not emp_name or not dept_name:
        if not emp_name and not dept_name:
            return None  # 空行跳过
        raise ValueError("姓名或部门为空")

    has_in = pd.notna(raw_in)
    has_out = pd.notna(raw_out)

    try:
        flag_val = int(raw_flag) if pd.notna(raw_flag) else 0
    except Exception:
        flag_val = 0

    if not has_in and not has_out and flag_val != 1:
        raise ValueError("缺少打卡时间")

    check_in_dt = pd.to_datetime(raw_in, errors='coerce') if has_in else None
    check_out_dt = pd.to_datetime(raw_out, errors='coerce') if has_out else None

    if has_in and pd.isna(check_in_dt):
        raise ValueError(f"上班时间格式错: {raw_in}")
    if has_out and pd.isna(check_out_dt):
        raise ValueError(f"下班时间格式错: {raw_out}")

    att_date = None
    if check_in_dt is not None and not pd.isna(check_in_dt):
        att_date = check_in_dt.date()
    elif check_out_dt is not None and not pd.isna(check_out_dt):
        att_date = check_out_dt.date()

    if not att_date:
        raise ValueError("无法确定日期")

    return {
        'emp_name': emp_name,
        'dept_name': dept_name,
        'check_in_dt': check_in_dt,
        'check_out_dt': check_out_dt,
        'flag_val': flag_val,
        'att_date': att_date,
    }


def parse_time_config(sys_config):
    """解析系统时间配置，返回默认值兜底"""
    try:
        work_start_str = sys_config.get('workStartTime', '09:00')
        work_end_str = sys_config.get('workEndTime', '18:00')
        if len(work_start_str) == 5:
            work_start_str += ':00'
        if len(work_end_str) == 5:
            work_end_str += ':00'
        return {
            'work_start_time': datetime.strptime(work_start_str, '%H:%M:%S').time(),
            'work_end_time': datetime.strptime(work_end_str, '%H:%M:%S').time(),
            'absent_threshold_hours': float(sys_config.get('absentThreshold', 4)),
            'late_threshold': int(sys_config.get('lateThreshold', 0)),
            'early_threshold': int(sys_config.get('earlyLeaveThreshold', 0)),
        }
    except Exception:
        return {
            'work_start_time': datetime.strptime('09:00:00', '%H:%M:%S').time(),
            'work_end_time': datetime.strptime('18:00:00', '%H:%M:%S').time(),
            'absent_threshold_hours': 4.0,
            'late_threshold': 0,
            'early_threshold': 0,
        }
