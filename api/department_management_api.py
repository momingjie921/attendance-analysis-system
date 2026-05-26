# api/department_management_api.py
from flask import request, jsonify
from sqlalchemy import or_
from models import db, Department, Employee
from utils.decorators import api_role_required
from utils.api_helpers import api_response
import re


@api_role_required(["admin"])
def get_department_list_full():
    """获取部门完整列表（用于管理页面）"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search = request.args.get('search', '').strip()

        # 构建查询
        query = Department.query

        # 搜索条件
        if search:
            query = query.outerjoin(Employee, Department.manager_id == Employee.emp_id).filter(
                or_(
                    Department.dept_name.like(f'%{search}%'),
                    Department.dept_code.like(f'%{search}%'),
                    Employee.emp_name.like(f'%{search}%')
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        departments = pagination.items

        # 获取每个部门的员工数量
        department_list = []
        for dept in departments:
            # 统计部门下的员工数量
            emp_count = Employee.query.filter_by(dept_id=dept.dept_id, status=1).count()

            # 获取父部门名称
            parent_name = ''
            if dept.parent_dept_id:
                parent_dept = Department.query.get(dept.parent_dept_id)
                if parent_dept:
                    parent_name = parent_dept.dept_name

            department_list.append({
                'dept_id': dept.dept_id,
                'dept_name': dept.dept_name,
                'dept_code': dept.dept_code,
                'manager_id': dept.manager_id,
                'manager_name': dept.manager.emp_name if dept.manager else '',
                'parent_dept_id': dept.parent_dept_id,
                'parent_dept_name': parent_name,
                'emp_count': emp_count,
                'status': dept.status,
                'create_time': dept.create_time.strftime('%Y-%m-%d %H:%M:%S') if dept.create_time else ''
            })

        data = {
            'departments': department_list,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages
        }

        return api_response(200, "获取部门列表成功", data)

    except Exception as e:
        return api_response(500, f"获取部门列表失败：{str(e)}")


@api_role_required(["admin"])
def create_department():
    """创建新部门"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['dept_name', 'dept_code']
        for field in required_fields:
            if field not in data or not data[field]:
                return api_response(400, f"缺少必填字段：{field}")

        # 验证格式
        name_pattern = re.compile(r'^[\u4e00-\u9fa5a-zA-Z]+$')
        if not name_pattern.match(data['dept_name']):
            return api_response(400, "部门名称只能包含中文和英文")

        code_pattern = re.compile(r'^[a-zA-Z0-9]+$')
        if not code_pattern.match(data['dept_code']):
            return api_response(400, "部门编码只能包含字母和数字")

        # 检查部门编码是否已存在
        if Department.query.filter_by(dept_code=data['dept_code']).first():
            return api_response(400, "部门编码已存在")

        # 验证上级部门是否存在
        parent_dept_id = data.get('parent_dept_id')
        if parent_dept_id:
            parent_dept = Department.query.get(parent_dept_id)
            if not parent_dept:
                return api_response(404, "上级部门不存在")

        # 验证部门负责人是否存在
        manager_id = data.get('manager_id')
        if manager_id:
            manager = Employee.query.get(manager_id)
            if not manager:
                return api_response(404, "部门负责人不存在")

        # 创建部门
        new_department = Department(
            dept_name=data['dept_name'],
            dept_code=data['dept_code'],
            manager_id=manager_id,
            parent_dept_id=parent_dept_id,
            status=data.get('status', 1)
        )

        db.session.add(new_department)
        db.session.commit()
        return api_response(200, f"创建部门 {new_department.dept_name} 成功", {'dept_id': new_department.dept_id})

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"创建部门失败：{str(e)}")


@api_role_required(["admin"])
def update_department():
    """更新部门信息"""
    try:
        data = request.get_json()
        dept_id = data.get('dept_id')

        if not dept_id:
            return api_response(400, "缺少部门ID")

        department = Department.query.get(dept_id)
        if not department:
            return api_response(404, "部门不存在")

        # 预先验证数据，避免在修改对象属性后触发autoflush导致的锁问题
        
        # 验证部门名称
        if 'dept_name' in data:
            name_pattern = re.compile(r'^[\u4e00-\u9fa5a-zA-Z]+$')
            if not name_pattern.match(data['dept_name']):
                return api_response(400, "部门名称只能包含中文和英文")

        # 验证部门编码
        if 'dept_code' in data and data['dept_code'] != department.dept_code:
            code_pattern = re.compile(r'^[a-zA-Z0-9]+$')
            if not code_pattern.match(data['dept_code']):
                return api_response(400, "部门编码只能包含字母和数字")
            
            existing = Department.query.filter_by(dept_code=data['dept_code']).first()
            if existing:
                return api_response(400, "部门编码已存在")

        # 验证负责人
        if 'manager_id' in data and data['manager_id']:
            manager = Employee.query.get(data['manager_id'])
            if not manager:
                return api_response(404, "部门负责人不存在")

        # 验证循环依赖
        if 'parent_dept_id' in data:
            parent_id = data['parent_dept_id']
            if parent_id == dept_id:
                return api_response(400, "不能设置自己为上级部门")

            if parent_id:
                parent_dept = Department.query.get(parent_id)
                if not parent_dept:
                    return api_response(404, "上级部门不存在")

                current = parent_dept
                while current.parent_dept_id:
                    if current.parent_dept_id == dept_id:
                        return api_response(400, "不能形成部门循环依赖")
                    current = Department.query.get(current.parent_dept_id)
                    if not current:
                        break

        # 所有验证通过后，再一次性应用修改
        if 'dept_name' in data:
            department.dept_name = data['dept_name']
        
        if 'dept_code' in data:
            department.dept_code = data['dept_code']
            
        if 'manager_id' in data:
            department.manager_id = data['manager_id']
            
        if 'parent_dept_id' in data:
            department.parent_dept_id = data['parent_dept_id']

        if 'status' in data:
            department.status = data['status']

        db.session.commit()

        return api_response(200, f"更新部门{department.dept_name}信息成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"更新部门信息失败：{str(e)}")


@api_role_required(["admin"])
def toggle_department_status():
    """切换部门状态（启用/禁用）"""
    try:
        data = request.get_json()
        dept_id = data.get('dept_id')
        status = data.get('status') # 0或1

        if not dept_id or status is None:
            return api_response(400, "缺少必要参数")

        department = Department.query.get(dept_id)
        if not department:
            return api_response(404, "部门不存在")

        # 逻辑更新
        department.status = status
        db.session.commit()

        action = "启用" if status == 1 else "禁用"
        return api_response(200, f"部门{department.dept_name}{action}成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"操作失败：{str(e)}")


@api_role_required(["admin"])
def permanent_delete_department():
    """永久删除部门（物理删除）"""
    try:
        data = request.get_json()
        dept_id = data.get('dept_id')

        if not dept_id:
            return api_response(400, "缺少部门ID")

        department = Department.query.get(dept_id)
        if not department:
            return api_response(404, "部门不存在")

        # 检查是否有子部门（包括禁用的）
        child_count = Department.query.filter_by(parent_dept_id=dept_id).count()
        if child_count > 0:
            return api_response(400, "该部门下有子部门，无法删除")

        # 检查是否有员工（包括离职的）
        emp_count = Employee.query.filter_by(dept_id=dept_id).count()
        if emp_count > 0:
            return api_response(400, "该部门下有员工，无法删除")

        # 物理删除
        dept_name = department.dept_name  # 保存名称用于返回消息
        db.session.delete(department)
        db.session.commit()

        return api_response(200, f"部门{dept_name}永久删除成功")

    except Exception as e:
        db.session.rollback()
        return api_response(500, f"删除部门失败：{str(e)}")


@api_role_required(["admin"])
def get_department_tree():
    """获取部门树形结构"""
    try:
        departments = Department.query.filter_by(status=1).all()

        # 构建部门树
        dept_dict = {}
        for dept in departments:
            dept_dict[dept.dept_id] = {
                'dept_id': dept.dept_id,
                'dept_name': dept.dept_name,
                'dept_code': dept.dept_code,
                'manager_name': dept.manager.emp_name if dept.manager else '',
                'parent_dept_id': dept.parent_dept_id,
                'children': []
            }

        # 构建树形结构
        dept_tree = []
        for dept_id, dept_data in dept_dict.items():
            parent_id = dept_data['parent_dept_id']
            if parent_id and parent_id in dept_dict:
                dept_dict[parent_id]['children'].append(dept_data)
            else:
                dept_tree.append(dept_data)

        return api_response(200, "获取部门树成功", {'tree': dept_tree})

    except Exception as e:
        return api_response(500, f"获取部门树失败：{str(e)}")
