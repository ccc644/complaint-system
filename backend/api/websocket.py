# 0724 WebSocket API 端点 — 实时推送通道
"""WebSocket 端点：接受客户端连接，JWT 认证，心跳保活。"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from core.websocket import manager
from middleware.auth import decode_access_token

logger = logging.getLogger("websocket")
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(default="", description="JWT Token"),
):
    """WebSocket 连接端点 — /api/ws?token=<jwt>

    客户端连接后，服务端：
    1. 验证 JWT Token
    2. 注册到 ConnectionManager
    3. 每隔 30 秒发送心跳 (ping)
    4. 断开时自动清理
    """
    # ── 1. 认证 ──
    if not token:
        await ws.close(code=4001, reason="缺少认证 Token")
        return

    payload = decode_access_token(token)
    if payload is None:
        await ws.close(code=4001, reason="Token 无效或已过期")
        return

    user_info = {
        "user_id": payload.get("user_id", 0),
        "username": payload.get("sub", ""),
        "display_name": payload.get("display_name", ""),
        "role": payload.get("role", ""),
        "position": payload.get("position", ""),
    }

    # ── 2. 注册连接 ──
    await manager.connect(ws, user_info)

    try:
        # ── 3. 心跳 + 消息接收循环 ──
        while True:
            try:
                # 等待客户端消息（或 30s 超时后发送心跳）
                data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                # 客户端可发送 "ping"，服务端回 "pong"
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                # 30 秒无消息 → 发送心跳 ping
                try:
                    await ws.send_text('{"type":"ping"}')
                except Exception:
                    break  # 发送失败 → 客户端已断开
    except WebSocketDisconnect:
        logger.info("WS client disconnected: user=%s", user_info.get("display_name", "?"))
    except Exception as e:
        logger.warning("WS error for user=%s: %s", user_info.get("display_name", "?"), e)
    finally:
        manager.disconnect(ws)
