# api/employee_management_api.py
from flask import request, jsonify
from sqlalchemy import or_
from datetime import datetime
from models import db, Employee, Department, User, Attendance, AbnormalAttendance
from utils.decorators import api_role_required
from utils.pagination import paginate_query, api_paginated_response
from utils.api_helpers import api_response


@api_role_required(["admin"])
def get_employee_list():
    """获取员工列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search = request.args.get('search', '').strip()
        dept_id = request.args.get('dept_id', type=int)
        status = request.args.get('status', type=int)
        has_account = request.args.get('has_account', type=int)

        # 构建查询
        query = Employee.query

        # 搜索条件
        if search:
            query = query.filter(
                or_(
                    Employee.emp_name.like(f'%{search}%'),
                    Employee.emp_code.like(f'%{search}%'),
                    Employee.phone.like(f'%{search}%'),
                    Employee.email.like(f'%{search}%')
                )
            )

        # 部门筛选
        if dept_id:
            query = query.filter_by(dept_id=dept_id)

        # 状态筛选
        if status is not None:
            query = query.filter_by(status=status)

        # 账户状态筛选
        if has_account is not None:
            if has_account == 1:
                # 筛选有账户的员工
                query = query.join(User, Employee.emp_id == User.emp_id)
            elif has_account == 0:
                # 筛选无账户的员工
                query = query.outerjoin(User, Employee.emp_id == User.emp_id).filter(User.user_id == None)

        # 分页查询
        pagination = paginate_query(query, page=page, per_page=per_page)

        # 构建响应数据
        employee_list = []
        for emp in pagination.items:
            # 查询对应的用户信息
            user = User.query.filter_by(emp_id=emp.emp_id).first()

            employee_list.append({
                'emp_id': emp.emp_id,
                'emp_code': emp.emp_code,
                'emp_name': emp.emp_name,
                'dept_id': emp.dept_id,
                'dept_name': emp.department.dept_name if emp.department else '',
                'phone': emp.phone or '',
                'email': emp.email or '',
                'entry_time': emp.entry_time.strftime('%Y-%m-%d') if emp.entry_time else '',
                'status': emp.status,
                'user_role': user.role if user else None,
                'username': user.username if user else None,
                'has_account': user is not None,  # 新增：是否有账户
                'create_time': emp.create_time.strftime('%Y-%m-%d %H:%M:%S') if emp.create_time else ''
            })

        return api_paginated_response(pagination, items=employee_list)

    except Exception as e:
        return api_response(500, f"获取员工列表失败：{str(e)}")


@api_role_required(["admin"])
def create_employee():
    """创建新员工"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['emp_code', 'emp_name', 'dept_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return api_response(400, f"缺少必填字段：{field}")

        # 检查员工编号是否已存在
        if Employee.query.filter_by(emp_code=data['emp_code']).first():
            return api_response(400, "员工编号已存在")

        # 检查手机号是否已存在
        if data.get('phone') and Employee.query.filter_by(phone=data['phone']).first():
            return api_response(400, "手机号已存在")

        # 检查邮箱是否已存在
        if data.get('email') and Employee.query.filter_by(email=data['email']).first():
            return api_response(400, "邮箱已存在")

        # 验证部门是否存在
        dept = Department.query.get(data['dept_id'])
        if not dept:
            return api_response(404, "部门不存在")

        # 处理入职时间
        entry_time = None
        if data.get('entry_time'):
            try:
                entry_time = datetime.strptime(data['entry_time'], '%Y-%m-%d').date()
            except ValueError:
                return api_response(400, "入职时间格式错误，请使用YYYY-MM-DD格式")

        # 创建员工记录
        new_employee = Employee(
            emp_code=data['emp_code'],
            emp_name=data['emp_name'],
            dept_id=data['dept_id'],
            phone=data.get('phone'),
            email=data.get('email'),
            entry_time=entry_time,
            status=data.get('status', 1)
        )

        db.session.add(new_employee)
        db.session.flush()  # 获取emp_id

        # 如果需要创建用户账户
        if data.get('create_user'):
            username = data.get('username', data['emp_code'])
            password = data.get('password', '123456')
            role = data.get('role', 'employee')

            # 检查用户名是否已存在
            if User.query.filter_by(username=username).first():
                db.session.rollback()
                return api_response(400, "用户名已存在")

            # 创建用户账户 - 使用构造函数传递密码
            new_user = User(
                username=username,
                emp_id=new_employee.emp_id,
                role=role,
                status=1,
                password=password  # 这里会触发set_password方法
            )

            db.session.add(new_user)

        db.session.commit()

        # 验证用户账户是否创建成功
        if data.get('create_user'):
            created_user = User.query.filter_by(username=username).first()

        return api_response(200, "创建员工成功", {
            'emp_id': new_employee.emp_id,
            'emp_code': new_employee.emp_code,
            'has_account': data.get('create_user', False)
        })

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"创建员工失败：{str(e)}")


@api_role_required(["admin"])
def update_employee():
    """更新员工信息"""
    try:
        data = request.get_json()
        emp_id = data.get('emp_id')

        if not emp_id:
            return api_response(400, "缺少员工ID")

        employee = Employee.query.get(emp_id)
        if not employee:
            return api_response(404, "员工不存在")

        # 更新字段
        if 'emp_name' in data:
            employee.emp_name = data['emp_name']

        # 修复问题1：更新员工编号
        if 'emp_code' in data:
            # 检查员工编号是否被其他员工使用
            if data['emp_code'] and data['emp_code'] != employee.emp_code:
                existing = Employee.query.filter_by(emp_code=data['emp_code']).first()
                if existing and existing.emp_id != emp_id:
                    return api_response(400, "员工编号已被其他员工使用")
            employee.emp_code = data['emp_code']

        if 'dept_id' in data:
            dept = Department.query.get(data['dept_id'])
            if not dept:
                return api_response(404, "部门不存在")
            employee.dept_id = data['dept_id']

        if 'phone' in data:
            # 检查手机号是否被其他员工使用
            if data['phone'] and data['phone'] != employee.phone:
                existing = Employee.query.filter_by(phone=data['phone']).first()
                if existing and existing.emp_id != emp_id:
                    return api_response(400, "手机号已被其他员工使用")
            employee.phone = data['phone']

        if 'email' in data:
            # 检查邮箱是否被其他员工使用
            if data['email'] and data['email'] != employee.email:
                existing = Employee.query.filter_by(email=data['email']).first()
                if existing and existing.emp_id != emp_id:
                    return api_response(400, "邮箱已被其他员工使用")
            employee.email = data['email']

        if 'entry_time' in data:
            try:
                employee.entry_time = datetime.strptime(data['entry_time'], '%Y-%m-%d').date()
            except ValueError:
                return api_response(400, "入职时间格式错误，请使用YYYY-MM-DD格式")

        if 'status' in data:
            employee.status = data['status']

            # 如果禁用员工，同时禁用对应的用户账户
            user = User.query.filter_by(emp_id=emp_id).first()
            if user:
                # 只有当员工被禁用时，才同步禁用用户账户
                if data['status'] == 0:
                    user.status = 0
                # 当员工恢复启用时，同步恢复用户账户
                elif data['status'] == 1:
                    user.status = 1

        # 处理用户账户 (创建/更新)
        if data.get('create_user'):
            username = data.get('username', employee.emp_code)
            password = data.get('password')
            role = data.get('role', 'employee')
            
            user = User.query.filter_by(emp_id=emp_id).first()
            if not user:
                # 创建新账户
                # 检查用户名是否已存在
                if User.query.filter_by(username=username).first():
                    return api_response(400, "用户名已存在")
                
                new_user = User(
                    username=username,
                    emp_id=emp_id,
                    role=role,
                    status=employee.status,
                    password=password if password else '123456'
                )
                db.session.add(new_user)
            else:
                # 更新现有账户
                if username and username != user.username:
                    if User.query.filter(User.username == username, User.user_id != user.user_id).first():
                        return api_response(400, "用户名已存在")
                    user.username = username
                
                if role:
                    user.role = role
                
                if password:
                    user.password = password

        db.session.commit()

        return api_response(200, "更新员工信息成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"更新员工信息失败：{str(e)}")


@api_role_required(["admin"])
def get_employee_detail():
    """获取单个员工详情"""
    try:
        emp_id = request.args.get('emp_id', type=int)
        if not emp_id:
            return api_response(400, "缺少员工ID")

        emp = Employee.query.get(emp_id)
        if not emp:
            return api_response(404, "员工不存在")

        # 查询对应的用户信息
        user = User.query.filter_by(emp_id=emp.emp_id).first()

        data = {
            'emp_id': emp.emp_id,
            'emp_code': emp.emp_code,
            'emp_name': emp.emp_name,
            'dept_id': emp.dept_id,
            'dept_name': emp.department.dept_name if emp.department else '',
            'phone': emp.phone or '',
            'email': emp.email or '',
            'entry_time': emp.entry_time.strftime('%Y-%m-%d') if emp.entry_time else '',
            'status': emp.status,
            'user_role': user.role if user else None,
            'username': user.username if user else None,
            'has_account': user is not None,
            'create_time': emp.create_time.strftime('%Y-%m-%d %H:%M:%S') if emp.create_time else ''
        }
        return api_response(200, "获取员工详情成功", data)
    except Exception as e:
        return api_response(500, f"获取员工详情失败：{str(e)}")


@api_role_required(["admin"])
def delete_employee():
    """删除员工（逻辑删除）"""
    try:
        data = request.get_json()
        emp_id = data.get('emp_id')

        if not emp_id:
            return api_response(400, "缺少员工ID")

        employee = Employee.query.get(emp_id)
        if not employee:
            return api_response(404, "员工不存在")

        # 逻辑删除：将状态设为0（离职/禁用）
        employee.status = 0

        # 同时禁用用户账户
        user = User.query.filter_by(emp_id=emp_id).first()
        if user:
            user.status = 0

        db.session.commit()

        return api_response(200, "员工删除成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"删除员工失败：{str(e)}")


@api_role_required(["admin"])
def get_department_list():
    """获取部门列表（用于下拉选择）"""
    try:
        departments = Department.query.filter_by(status=1).all()

        dept_list = [{
            'dept_id': dept.dept_id,
            'dept_name': dept.dept_name,
            'dept_code': dept.dept_code,
            'manager_name': dept.manager.emp_name if dept.manager else ''
        } for dept in departments]

        return api_response(200, "获取部门列表成功", {'departments': dept_list})

    except Exception as e:
        return api_response(500, f"获取部门列表失败：{str(e)}")


@api_role_required(["admin"])
def create_user_account():
    """为已有员工创建用户账户"""
    try:
        data = request.get_json()
        emp_id = data.get('emp_id')

        if not emp_id:
            return api_response(400, "缺少员工ID")

        # 检查员工是否存在
        employee = Employee.query.get(emp_id)
        if not employee:
            return api_response(404, "员工不存在")

        # 检查是否已有用户账户
        existing_user = User.query.filter_by(emp_id=emp_id).first()
        if existing_user:
            return api_response(400, "该员工已有用户账户")

        # 获取账户信息
        username = data.get('username', employee.emp_code)
        password = data.get('password', '123456')
        role = data.get('role', 'employee')

        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return api_response(400, "用户名已存在")

        # 创建用户账户
        new_user = User(
            username=username,
            emp_id=emp_id,
            role=role,
            status=1
        )
        new_user.password_hash = password  # 使用正确的密码设置方式

        db.session.add(new_user)
        db.session.commit()

        return api_response(200, "创建用户账户成功", {
            'username': username,
            'emp_name': employee.emp_name,
            'role': role
        })

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"创建用户账户失败：{str(e)}")


@api_role_required(["admin"])
def reset_user_password():
    """重置用户密码"""
    try:
        data = request.get_json()
        emp_id = data.get('emp_id')
        new_password = data.get('password', '123456')

        if not emp_id:
            return api_response(400, "缺少员工ID")

        # 查找用户账户
        user = User.query.filter_by(emp_id=emp_id).first()
        if not user:
            return api_response(404, "该员工没有用户账户")

        # 重置密码
        user.password_hash = new_password

        db.session.commit()

        return api_response(200, "密码重置成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"重置密码失败：{str(e)}")


@api_role_required(["admin"])
def permanent_delete_employee():
    """永久删除员工（物理删除，包括相关数据）"""
    try:
        data = request.get_json()
        emp_id = data.get('emp_id')

        if not emp_id:
            return api_response(400, "缺少员工ID")

        employee = Employee.query.get(emp_id)
        if not employee:
            return api_response(404, "员工不存在")

        emp_name = employee.emp_name  # 记录员工姓名用于返回信息

        # 检查是否有关联数据，防止级联删除错误
        # 1. 删除关联的用户账户
        user = User.query.filter_by(emp_id=emp_id).first()
        if user:
            db.session.delete(user)

        # 2. 删除考勤记录
        attendances = Attendance.query.filter_by(emp_id=emp_id).all()
        for attendance in attendances:
            db.session.delete(attendance)

        # 3. 删除异常考勤记录
        abnormal_attendances = AbnormalAttendance.query.filter_by(emp_id=emp_id).all()
        for abnormal in abnormal_attendances:
            db.session.delete(abnormal)

        # 4. 删除请假记录（如果有Leave表）
        try:
            from models.leave import Leave
            leaves = Leave.query.filter_by(emp_id=emp_id).all()
            for leave in leaves:
                db.session.delete(leave)
        except Exception as e:
            pass

        # 5. 最后删除员工记录
        db.session.delete(employee)
        db.session.commit()

        return api_response(200, f"员工【{emp_name}】已永久删除", {
            'emp_name': emp_name,
            'emp_id': emp_id
        })

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"永久删除员工失败：{str(e)}")