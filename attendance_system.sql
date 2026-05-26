/*
 Navicat Premium Dump SQL

 Source Server         : localhost_3306
 Source Server Type    : MySQL
 Source Server Version : 80409 (8.4.9)
 Source Host           : localhost:3306
 Source Schema         : attendance_system

 Target Server Type    : MySQL
 Target Server Version : 80409 (8.4.9)
 File Encoding         : 65001

 Date: 27/05/2026 01:12:38
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for abnormal_attendance
-- ----------------------------
DROP TABLE IF EXISTS `abnormal_attendance`;
CREATE TABLE `abnormal_attendance`  (
  `abnormal_id` bigint UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '异常记录ID',
  `emp_id` int UNSIGNED NOT NULL COMMENT '员工ID',
  `abnormal_date` date NOT NULL COMMENT '异常日期',
  `abnormal_type` enum('LATE','EARLY','ABSENT','MISSING_CHECK') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '异常类型：late/early/absent/missing_check',
  `abnormal_desc` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '异常描述',
  `is_processed` smallint NOT NULL DEFAULT 0 COMMENT '是否已处理：1-是 0-否',
  `processor_id` int UNSIGNED NULL DEFAULT NULL COMMENT '处理人ID',
  `process_remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '处理备注',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`abnormal_id`) USING BTREE,
  UNIQUE INDEX `uq_emp_date_type`(`emp_id` ASC, `abnormal_date` ASC, `abnormal_type` ASC) USING BTREE,
  INDEX `processor_id`(`processor_id` ASC) USING BTREE,
  INDEX `idx_is_processed`(`is_processed` ASC) USING BTREE,
  INDEX `idx_abnormal_date`(`abnormal_date` ASC) USING BTREE,
  INDEX `idx_emp_id`(`emp_id` ASC) USING BTREE,
  CONSTRAINT `abnormal_attendance_ibfk_1` FOREIGN KEY (`emp_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `abnormal_attendance_ibfk_2` FOREIGN KEY (`processor_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 36138 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for attendance_record
-- ----------------------------
DROP TABLE IF EXISTS `attendance_record`;
CREATE TABLE `attendance_record`  (
  `att_id` bigint UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '考勤记录ID',
  `emp_id` int UNSIGNED NOT NULL COMMENT '关联员工ID',
  `att_date` date NOT NULL COMMENT '考勤日期',
  `check_in_time` datetime NULL DEFAULT NULL COMMENT '上班打卡时间（NULL为未打卡）',
  `check_out_time` datetime NULL DEFAULT NULL COMMENT '下班打卡时间（NULL为未打卡）',
  `late_minutes` int NULL DEFAULT NULL COMMENT '迟到分钟数（0为未迟到）',
  `early_minutes` int NULL DEFAULT NULL COMMENT '早退分钟数（0为未早退）',
  `work_duration` int NULL DEFAULT NULL COMMENT '当日工作时长（分钟，NULL为未统计）',
  `is_absent` smallint NOT NULL DEFAULT 0 COMMENT '是否旷工：1-是 0-否（结合请假表判定）',
  `import_batch` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '数据导入批次号（关联import_log表）',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`att_id`) USING BTREE,
  UNIQUE INDEX `uk_emp_date`(`emp_id` ASC, `att_date` ASC) USING BTREE,
  INDEX `idx_att_date`(`att_date` ASC) USING BTREE,
  INDEX `idx_emp_id`(`emp_id` ASC) USING BTREE,
  CONSTRAINT `attendance_record_ibfk_1` FOREIGN KEY (`emp_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 168603 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for department
-- ----------------------------
DROP TABLE IF EXISTS `department`;
CREATE TABLE `department`  (
  `dept_id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '部门唯一ID',
  `dept_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '部门名称',
  `dept_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '部门编码',
  `manager_id` int UNSIGNED NULL DEFAULT NULL COMMENT '部门负责人ID',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系电话',
  `email` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱地址',
  `parent_dept_id` int UNSIGNED NULL DEFAULT NULL COMMENT '上级部门ID（NULL为一级部门）',
  `status` smallint NOT NULL DEFAULT 1 COMMENT '状态：1-启用 0-禁用',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`dept_id`) USING BTREE,
  UNIQUE INDEX `dept_code`(`dept_code` ASC) USING BTREE,
  INDEX `idx_manager_id`(`manager_id` ASC) USING BTREE,
  INDEX `idx_parent_dept_id`(`parent_dept_id` ASC) USING BTREE,
  CONSTRAINT `department_ibfk_1` FOREIGN KEY (`parent_dept_id`) REFERENCES `department` (`dept_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `department_ibfk_2` FOREIGN KEY (`manager_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 203 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for employee
-- ----------------------------
DROP TABLE IF EXISTS `employee`;
CREATE TABLE `employee`  (
  `emp_id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '员工唯一ID',
  `emp_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '员工姓名',
  `emp_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '员工编号',
  `dept_id` int UNSIGNED NOT NULL COMMENT '所属部门ID',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '手机号',
  `email` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱',
  `entry_time` date NULL DEFAULT NULL COMMENT '入职时间',
  `status` smallint NOT NULL DEFAULT 1 COMMENT '状态：1-在职 0-离职',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`emp_id`) USING BTREE,
  UNIQUE INDEX `emp_code`(`emp_code` ASC) USING BTREE,
  UNIQUE INDEX `phone`(`phone` ASC) USING BTREE,
  UNIQUE INDEX `email`(`email` ASC) USING BTREE,
  INDEX `dept_id`(`dept_id` ASC) USING BTREE,
  CONSTRAINT `employee_ibfk_1` FOREIGN KEY (`dept_id`) REFERENCES `department` (`dept_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1036 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for holiday_calendar
-- ----------------------------
DROP TABLE IF EXISTS `holiday_calendar`;
CREATE TABLE `holiday_calendar`  (
  `holiday_date` date NOT NULL COMMENT '日期',
  `is_workday` smallint NOT NULL COMMENT '是否工作日：1-工作日 0-节假日/休息日',
  `name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '名称',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`holiday_date`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for import_log
-- ----------------------------
DROP TABLE IF EXISTS `import_log`;
CREATE TABLE `import_log`  (
  `log_id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `import_batch` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '导入批次号',
  `import_user_id` int UNSIGNED NOT NULL COMMENT '导入人ID（关联user）',
  `file_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '导入文件名',
  `file_size` bigint UNSIGNED NULL DEFAULT NULL COMMENT '文件大小（字节）',
  `total_rows` int UNSIGNED NULL DEFAULT NULL COMMENT '文件总行数',
  `success_rows` int UNSIGNED NULL DEFAULT NULL COMMENT '导入成功行数',
  `fail_rows` int UNSIGNED NULL DEFAULT NULL COMMENT '导入失败行数',
  `fail_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '失败原因（JSON格式存储）',
  `import_status` enum('success','failed','processing','success_with_errors') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '导入状态',
  `create_time` datetime NULL DEFAULT NULL COMMENT '导入时间',
  PRIMARY KEY (`log_id`) USING BTREE,
  UNIQUE INDEX `import_batch`(`import_batch` ASC) USING BTREE,
  INDEX `idx_import_user_id`(`import_user_id` ASC) USING BTREE,
  CONSTRAINT `import_log_ibfk_1` FOREIGN KEY (`import_user_id`) REFERENCES `user` (`user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for leave_record
-- ----------------------------
DROP TABLE IF EXISTS `leave_record`;
CREATE TABLE `leave_record`  (
  `leave_id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '请假记录ID',
  `emp_id` int UNSIGNED NOT NULL COMMENT '关联员工ID',
  `leave_type` enum('annual','sick','personal','maternity','other') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '请假类型',
  `start_date` date NOT NULL COMMENT '请假开始日期',
  `end_date` date NOT NULL COMMENT '请假结束日期',
  `leave_days` decimal(3, 1) NOT NULL COMMENT '请假天数（如0.5天）',
  `leave_half_day` enum('AM','PM') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '半天请假：AM-上午 PM-下午',
  `approval_status` enum('pending','approved','rejected') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '审批状态',
  `approver_id` int UNSIGNED NULL DEFAULT NULL COMMENT '审批人ID（关联employee）',
  `approval_remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '审批备注',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '请假备注',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`leave_id`) USING BTREE,
  INDEX `approver_id`(`approver_id` ASC) USING BTREE,
  INDEX `idx_emp_id`(`emp_id` ASC) USING BTREE,
  INDEX `idx_start_end_date`(`start_date` ASC, `end_date` ASC) USING BTREE,
  CONSTRAINT `chk_leave_date_range` CHECK (`start_date` <= `end_date`),
  CONSTRAINT `chk_leave_days_positive` CHECK (`leave_days` > 0),
  CONSTRAINT `leave_record_ibfk_1` FOREIGN KEY (`emp_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_record_ibfk_2` FOREIGN KEY (`approver_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 3314 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for system_config
-- ----------------------------
DROP TABLE IF EXISTS `system_config`;
CREATE TABLE `system_config`  (
  `config_id` int NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `config_key` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置键',
  `config_value` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置值',
  `config_desc` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '配置说明',
  `config_type` enum('time','number','string') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置类型',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`config_id`) USING BTREE,
  UNIQUE INDEX `config_key`(`config_key` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 14 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for user
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user`  (
  `user_id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户唯一ID',
  `emp_id` int UNSIGNED NOT NULL COMMENT '关联员工ID',
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录账号',
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '加密密码（SHA256+盐值）',
  `role` enum('admin','manager','employee') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'employee' COMMENT '角色',
  `last_login_time` datetime NULL DEFAULT NULL COMMENT '最后登录时间',
  `status` smallint NOT NULL DEFAULT 1 COMMENT '状态：1-启用 0-禁用',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`user_id`) USING BTREE,
  UNIQUE INDEX `emp_id`(`emp_id` ASC) USING BTREE,
  UNIQUE INDEX `username`(`username` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_username`(`username` ASC) USING BTREE,
  INDEX `idx_role`(`role` ASC) USING BTREE,
  CONSTRAINT `user_ibfk_1` FOREIGN KEY (`emp_id`) REFERENCES `employee` (`emp_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 734 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
