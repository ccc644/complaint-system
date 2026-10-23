# 0727 Phase 4 用户管理业务逻辑层
# 0819 v3.0：角色直接下拉选择，新增职位（position）必填
"""用户管理业务逻辑 — 校验/编排，数据库操作委托给 data.database。

三层分离约定：本模块不触碰 FastAPI（不抛 HTTPException），
校验失败抛出 UserServiceError，由 API 层转换为 HTTP 响应。
"""

from data import database as db


class UserServiceError(Exception):
    """用户管理业务校验失败。status_code 供 API 层映射为 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── 输出脱敏 ──────────────────────────────────────
def _sanitize(user: dict) -> dict:
    """移除敏感字段（密码哈希/可逆密文），统一布尔/缺省值。0819 输出角色+职位；0824 增钉钉绑定。"""
    return {
        "id": user.get("id"),
        "username": user.get("username", ""),
        "display_name": user.get("display_name", ""),
        "role": user.get("role", ""),
        "position": user.get("position", ""),
        "dingtalk_userid": user.get("dingtalk_userid", "") or "",
        "is_active": bool(user.get("is_active", 1)),
        "created_at": user.get("created_at", "") or "",
    }


def _validate_dingtalk_userid(value: str) -> str:
    """0824 校验钉钉UserID：strip、≤64、不含空白；空串=未绑定（合法）。"""
    du = (value or "").strip()
    if len(du) > 64:
        raise UserServiceError("钉钉UserID长度不能超过 64 字符")
    if du and any(ch.isspace() for ch in du):
        raise UserServiceError("钉钉UserID不能包含空格")
    return du


def get_meta() -> dict:
    """0819 下拉选项元数据：仅角色列表。"""
    return {
        "roles": list(db.ALL_ROLES),
    }


def list_users(role_filter: str = "", include_inactive: bool = False) -> list[dict]:
    """列出用户（脱敏），支持角色筛选。"""
    users = db.list_users(role_filter, "", include_inactive)
    return [_sanitize(u) for u in users]


def create_user(username: str, password: str, display_name: str,
                role: str, position: str, dingtalk_userid: str = "") -> int:
    """0819 创建用户：账号 + 密码 + 显示名 + 角色下拉 + 职位必填；0824 增钉钉UserID（选填）。"""
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    position = (position or "").strip()

    if not username or not display_name or not password:
        raise UserServiceError("账号、显示名和密码不能为空")
    if len(password) < 4:
        raise UserServiceError("密码至少 4 位")
    if role not in db.ALL_ROLES:
        raise UserServiceError(f"无效角色：{role}，有效值：{', '.join(db.ALL_ROLES)}")
    if not position:
        raise UserServiceError("公司职位不能为空")
    du = _validate_dingtalk_userid(dingtalk_userid)
    if db.get_user_by_username(username):
        raise UserServiceError(f"账号「{username}」已存在", status_code=409)

    uid = db.create_user(
        username=username,
        password=password,
        display_name=display_name,
        role=role,
        position=position,
        dingtalk_userid=du,
    )
    if uid is None:
        raise UserServiceError(f"账号「{username}」已存在", status_code=409)
    return uid


def update_user(user_id: int, fields: dict) -> dict:
    """0819 更新用户属性（显示名/角色/职位/启用），返回更新后的用户（脱敏）。"""
    target = db.get_user_by_id(user_id)
    if not target:
        raise UserServiceError("用户不存在", status_code=404)

    updates: dict = {}
    if fields.get("display_name") is not None:
        name = fields["display_name"].strip()
        if not name:
            raise UserServiceError("显示名不能为空")
        updates["display_name"] = name

    if fields.get("role") is not None:
        if fields["role"] not in db.ALL_ROLES:
            raise UserServiceError(f"无效角色：{fields['role']}")
        updates["role"] = fields["role"]

    if fields.get("position") is not None:
        pos = fields["position"].strip()
        if not pos:
            raise UserServiceError("公司职位不能为空")
        updates["position"] = pos

    # 0824 钉钉绑定：可清空（空串=解绑）
    if fields.get("dingtalk_userid") is not None:
        updates["dingtalk_userid"] = _validate_dingtalk_userid(fields["dingtalk_userid"])

    if fields.get("is_active") is not None:
        if not fields["is_active"] and target.get("username") == "admin":
            raise UserServiceError("系统管理员账号不可停用", status_code=409)
        updates["is_active"] = 1 if fields["is_active"] else 0

    if not updates:
        raise UserServiceError("没有需要更新的字段")

    db.update_user(user_id, **updates)
    return _sanitize(db.get_user_by_id(user_id))


def reset_password(user_id: int, new_password: str) -> None:
    """重置用户密码（至少 4 位）。"""
    if not db.get_user_by_id(user_id):
        raise UserServiceError("用户不存在", status_code=404)
    if not new_password or len(new_password) < 4:
        raise UserServiceError("密码至少 4 位")
    db.reset_password(user_id, new_password)


def delete_user(user_id: int) -> None:
    """硬删除用户。主管理员不可删除。"""
    target = db.get_user_by_id(user_id)
    if not target:
        raise UserServiceError("用户不存在", status_code=404)
    if target.get("username") == "admin":
        raise UserServiceError("系统管理员账号不可删除", status_code=409)
    ok = db.delete_user(user_id)
    if not ok:
        raise UserServiceError("删除失败", status_code=409)


def deactivate_user(user_id: int) -> None:
    """停用用户（软删除）。主管理员不可停用。"""
    target = db.get_user_by_id(user_id)
    if not target:
        raise UserServiceError("用户不存在", status_code=404)
    if target.get("username") == "admin":
        raise UserServiceError("系统管理员账号不可停用", status_code=409)
    ok = db.deactivate_user(user_id)
    if not ok:
        raise UserServiceError("停用失败", status_code=409)
