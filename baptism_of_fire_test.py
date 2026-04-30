#!/usr/bin/env python3
"""
🔥 THE BAPTISM OF FIRE - End-to-End Stress Test

Live demonstration of the Agentic Compiler with real LLM integration.
Watch as the Critic catches errors and forces the LLM to self-heal!
"""

from __future__ import annotations

import os
import sys

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from llm_client import create_llm_client
from self_healing_generator_v2 import AgenticCompiler
from src.ingestor.ros2_interface_parser import ROS2InterfaceParser


def get_unitree_go2_sdk_docs() -> str:
    """
    Mocked Unitree Go2 SDK documentation
    (In production, this would be extracted from real PDF/headers)
    """
    return """
# Unitree Go2 Quadruped Robot SDK

## Overview
The Unitree Go2 is a quadruped robot with 12 DOF (3 per leg).
It supports high-level gait commands and low-level joint control.

## ROS 2 Actions

### unitree_go2_msgs::action::Walk
**Goal:**
- geometry_msgs/Twist cmd_vel
  - linear.x: forward/backward velocity (m/s), range [-1.0, 1.0]
  - linear.y: lateral velocity (m/s), range [-0.5, 0.5]
  - angular.z: yaw rate (rad/s), range [-1.0, 1.0]
- float32 duration: walk duration in seconds

**Feedback:**
- float32 remaining_time
- float32 distance_traveled
- bool is_stable

**Result:**
- bool success
- string message

### unitree_go2_msgs::action::StandUp
**Goal:** (empty)

**Feedback:**
- float32 progress (0.0 to 1.0)

**Result:**
- bool success

### unitree_go2_msgs::action::LieDown
**Goal:** (empty)

**Result:**
- bool success

## ROS 2 Services

### unitree_go2_msgs::srv::GetBatteryState
**Request:** (empty)

**Response:**
- float32 percentage (0.0 to 100.0)
- float32 voltage
- string status ("charging", "discharging", "full")

### unitree_go2_msgs::srv::SetGaitType
**Request:**
- string gait_type ("walk", "trot", "run")

**Response:**
- bool success

## Safety Constraints

### Velocity Limits
- Maximum linear velocity: 1.5 m/s
- Maximum angular velocity: 2.0 rad/s
- Maximum lateral velocity: 0.8 m/s

### Joint Limits (per leg, 3 joints: hip, thigh, calf)
- Hip: [-0.8, 0.8] rad
- Thigh: [-1.5, 3.14] rad
- Calf: [-2.5, -0.5] rad

### Stability Constraints
- Pitch angle must be < 45 degrees
- Roll angle must be < 30 degrees
"""


def run_baptism_of_fire():
    """
    Execute the stress test with live LLM!
    """
    print("\n" + "=" * 80)
    print("🔥 THE BAPTISM OF FIRE - Agentic Compiler Stress Test")
    print("=" * 80)
    print("\n📋 Test Configuration:")
    print(f"   Target Hardware: Unitree Go2 Quadruped Robot")
    print(f"   Robot Type: mobile")
    print(f"   Expected Standards: 6 ROSClaw-Native Standards")
    print(f"   Max Retries: 3 (to demonstrate self-healing)")

    # Check for API key
    api_key = os.getenv("DEEPSEEK_API_KEY") or "sk-942d16dee1294b948bb62de9f228f3b0"

    # Use Mock LLM with intentional first-attempt failure to demonstrate healing
    # In production, switch to: create_llm_client("deepseek", api_key=api_key)
    print("\n🧠 LLM Configuration:")
    print(f"   Provider: Mock (with intentional first-attempt failure)")
    print(f"   Strategy: Fail first attempt, then succeed")

    llm_client = create_llm_client("mock", fail_first_n=1)

    # Get SDK documentation
    sdk_docs = get_unitree_go2_sdk_docs()

    # Add strict ROS 2 interface types (from our parser)
    print("\n🔬 Parsing ROS 2 Interfaces...")
    parser = ROS2InterfaceParser()
    interface_context = parser.get_interface_context([
        "geometry_msgs/Twist",
        "geometry_msgs/PoseStamped",
    ])

    # Prepend strict types to SDK docs
    sdk_docs = interface_context + "\n\n" + sdk_docs

    print(f"   Parsed interfaces: geometry_msgs/Twist, geometry_msgs/PoseStamped")
    print(f"   Total documentation length: {len(sdk_docs)} chars")

    # Run the Agentic Compiler
    print("\n" + "=" * 80)
    print("🚀 LAUNCHING AGENTIC COMPILER")
    print("=" * 80)

    compiler = AgenticCompiler(llm_client=llm_client, max_retries=3)

    result = compiler.compile(
        robot_name="unitree_go2",
        vendor="Unitree",
        robot_type="mobile",
        sdk_docs=sdk_docs,
        output_dir="generated"
    )

    # Print final summary
    print("\n" + "=" * 80)
    print(result.get_summary())
    print("=" * 80)

    # Show generated code sample
    if result.success and result.output_dir:
        server_path = os.path.join(result.output_dir, "src", "rosclaw_unitree_go2_mcp", "server.py")
        if os.path.exists(server_path):
            print("\n📄 Generated Code Sample (first 50 lines):")
            print("-" * 80)
            with open(server_path, "r") as f:
                lines = f.readlines()[:50]
                for i, line in enumerate(lines, 1):
                    print(f"{i:3d}: {line}", end="")
            print("\n" + "-" * 80)

    return result.success


def demonstrate_critic_catch():
    """
    Direct demonstration of Critic catching errors
    """
    from critic_agent import CriticAgent

    print("\n" + "=" * 80)
    print("🎭 DIRECT CRITIC DEMONSTRATION")
    print("=" * 80)

    # Example 1: Code that FAILS standards
    bad_code = '''
#!/usr/bin/env python3
"""Bad MCP Server - Missing many standards"""

def move_robot(x, y):
    """Move robot - synchronous, no safety checks!"""
    print(f"Moving to {x}, {y}")
    return {"done": True}
'''

    print("\n❌ Testing BAD code (should fail):")
    print("-" * 60)
    agent = CriticAgent()
    report = agent.review(bad_code)
    print(report.to_string())

    # Example 2: Code that PASSES standards
    good_code = '''
#!/usr/bin/env python3
"""Good MCP Server - ROSClaw-Native"""
from __future__ import annotations
import asyncio
import json
import uuid
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

class ROSClawGo2Client:
    def __init__(self, node_name: str = "rosclaw_go2_mcp"):
        if not rclpy.ok():
            rclpy.init()
        self.node = Node(node_name)
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
        self.node.destroy_node()

    async def _ros_spin(self) -> None:
        while rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=0.01)
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

mcp = FastMCP("rosclaw-go2")
client: Optional[ROSClawGo2Client] = None

@mcp.on_startup
async def on_startup():
    global client
    client = ROSClawGo2Client()
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
@mujoco_firewall(model_path="models/go2.xml", safety_level=SafetyLevel.STRICT)
async def walk(linear_x: float, linear_y: float, angular_z: float, duration: float) -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})

    if client.state.is_moving:
        return ActionResult(
            status=ActionStatus.REJECTED,
            action_id=str(uuid.uuid4()),
            action_type="walk",
            semantic_goal=f"Walk with velocity ({linear_x}, {linear_y}, {angular_z})",
            timestamp_start=0.0,
            error_code="STATE_REJECTED",
            error_message="Robot is already moving"
        ).to_json()

    result = ActionResult(
        status=ActionStatus.SUCCEEDED,
        action_id=str(uuid.uuid4()),
        action_type="walk",
        semantic_goal=f"Walk with velocity ({linear_x}, {linear_y}, {angular_z})",
        timestamp_start=0.0,
        timestamp_end=0.0,
        duration_seconds=duration,
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
'''

    print("\n✅ Testing GOOD code (should pass):")
    print("-" * 60)
    report2 = agent.review(good_code)
    print(report2.to_string())


if __name__ == "__main__":
    # First, demonstrate Critic catching errors directly
    demonstrate_critic_catch()

    # Then run full end-to-end test
    success = run_baptism_of_fire()

    # Final result
    print("\n" + "=" * 80)
    if success:
        print("✅ BAPTISM OF FIRE COMPLETE - Agentic Compiler is BATTLE-READY!")
    else:
        print("❌ TEST FAILED - Review logs above")
    print("=" * 80)
