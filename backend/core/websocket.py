# 0724 WebSocket 连接管理器 — 实时推送工单状态变更
# 0819 v3.0：仅按角色分组广播（部门概念取消）
"""WebSocket 连接管理：按角色分组，支持定向广播。

基于 FastAPI 原生 WebSocket，无需额外依赖。
每个连接对应一个用户（role + user_id + position），
广播时可精确推送到目标角色。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("websocket")


class ConnectionManager:
    """WebSocket 连接管理器（单例模式）。"""

    def __init__(self):
        # active_connections: WebSocket -> 用户元信息
        self._connections: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, ws: WebSocket, user_info: dict[str, Any]) -> None:
        """接受 WebSocket 连接并注册用户信息。"""
        await ws.accept()
        self._connections[ws] = user_info
        logger.info(
            "WS connected: user=%s role=%s (total=%d)",
            user_info.get("display_name", "?"),
            user_info.get("role", "?"),
            len(self._connections),
        )

    def disconnect(self, ws: WebSocket) -> None:
        """断开连接并移除注册信息。"""
        info = self._connections.pop(ws, None)
        logger.info(
            "WS disconnected: user=%s (total=%d)",
            info.get("display_name", "?") if info else "?",
            len(self._connections),
        )

    async def broadcast(self, event: dict[str, Any],
                        target_role: str | None = None,
                        target_dept: str | None = None) -> int:
        """广播事件到匹配的客户端。

        Args:
            event: 事件 dict，包含 type / complaint_id / status 等字段。
            target_role: 目标角色（"全员" 表示广播所有；None 不限定角色）。
            target_dept: 0819 已弃用，保留签名兼容。

        Returns:
            实际发送到的客户端数量。
        """
        message = json.dumps(event, ensure_ascii=False)
        count = 0
        closed: list[WebSocket] = []

        for ws, info in self._connections.items():
            # 角色过滤
            if target_role and target_role != "全员":
                if info.get("role") != target_role:
                    continue

            try:
                await ws.send_text(message)
                count += 1
            except Exception:
                closed.append(ws)

        # 清理已断开的连接
        for ws in closed:
            self.disconnect(ws)

        logger.debug("WS broadcast: type=%s → %d clients", event.get("type"), count)
        return count

    @property
    def active_count(self) -> int:
        """当前活跃连接数。"""
        return len(self._connections)


# 全局单例
manager = ConnectionManager()
