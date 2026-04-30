
#!/usr/bin/env python3
"""ROSClaw-Native MCP Server"""

from __future__ import annotations
import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from mcp.server.fastmcp import FastMCP
from rosclaw.firewall.decorator import mujoco_firewall, SafetyLevel

class ActionStatus(Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"

@dataclass
class ActionResult:
    status: ActionStatus
    action_id: str
    action_type: str
    semantic_goal: str
    timestamp_start: float
    timestamp_end: Optional[float] = None
    duration_seconds: Optional[float] = None
    success: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    firewall_validated: bool = False
    safety_violations: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "status": self.status.value,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "semantic_goal": self.semantic_goal,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error": {"code": self.error_code, "message": self.error_message},
            "safety": {"firewall_validated": self.firewall_validated, "violations": self.safety_violations}
        }, indent=2)

@dataclass
class RobotState:
    is_moving: bool = False
    is_standing: bool = False
    last_action_id: Optional[str] = None

class ROSClawTestClient:
    def __init__(self):
        self.state = RobotState()
        self._active_tasks: Dict[str, Any] = {}
        self._spin_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._spin_task = asyncio.create_task(self._ros_spin())

    async def stop(self) -> None:
        if self._spin_task:
            self._spin_task.cancel()
            try:
                await self._spin_task
            except asyncio.CancelledError:
                pass

    async def _ros_spin(self) -> None:
        while True:
            await asyncio.sleep(0.001)

    async def cancel_action(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self._active_tasks:
            return {"success": False, "error": f"No active action with ID: {task_id}"}
        goal_handle = self._active_tasks[task_id]
        try:
            cancel_future = goal_handle.cancel_goal_async()
            cancel_result = await self._await_future(cancel_future)
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            return {"success": True, "message": f"Action {task_id} canceled"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _await_future(self, future: Any, timeout: float = 30.0) -> Any:
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        while not future.done():
            if loop.time() - start_time > timeout:
                raise TimeoutError(f"Future timeout after {timeout}s")
            await asyncio.sleep(0.01)
        return future.result()

mcp = FastMCP("rosclaw-test")
client: Optional[ROSClawTestClient] = None

@mcp.on_startup
async def on_startup():
    global client
    client = ROSClawTestClient()
    await client.start()

@mcp.on_shutdown
async def on_shutdown():
    global client
    if client:
        await client.stop()

@mcp.tool()
async def get_state() -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})
    return json.dumps({
        "is_moving": client.state.is_moving,
        "is_standing": client.state.is_standing,
    })

@mcp.tool()
@mujoco_firewall(safety_level=SafetyLevel.STRICT)
async def move_robot(x: float, y: float) -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})

    if client.state.is_moving:
        return ActionResult(
            status=ActionStatus.REJECTED,
            action_id=str(uuid.uuid4()),
            action_type="move_robot",
            semantic_goal=f"Move to ({x}, {y})",
            timestamp_start=time.time(),
            error_code="STATE_REJECTED",
            error_message="Robot is already moving"
        ).to_json()

    await asyncio.sleep(0.1)

    result = ActionResult(
        status=ActionStatus.SUCCEEDED,
        action_id=str(uuid.uuid4()),
        action_type="move_robot",
        semantic_goal=f"Move to ({x}, {y})",
        timestamp_start=time.time(),
        timestamp_end=time.time(),
        duration_seconds=0.1,
        success=True,
        firewall_validated=True
    )
    return result.to_json()

@mcp.tool()
async def cancel_action_tool(task_id: str) -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})
    result = await client.cancel_action(task_id)
    return json.dumps(result)
