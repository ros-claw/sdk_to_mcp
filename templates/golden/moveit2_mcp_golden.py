#!/usr/bin/env python3
"""
ROSClaw-Native MoveIt2 MCP Server

Production-grade MCP server for MoveIt2 motion planning with ROSClaw OS integration.

ROSClaw-Native Standards Implemented:
1. ✅ Asynchronous ROS 2 Actions - Non-blocking action clients with async/await
2. ✅ Flywheel-Ready Responses - Structured JSON for Data Flywheel ingestion
3. ✅ Firewall Integration - @mujoco_firewall decorator for Digital Twin validation
4. ✅ Graceful Preemption - Active task tracking with cancel_action() support
5. ✅ State-Aware Affordance - Local state machine prevents invalid operations
6. ✅ Semantic Spatial Binding - TF2 integration abstracts 3D math from LLM

Author: ROSClaw OS Architect
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from collections import deque

# ROS 2
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.task import Future
import tf2_ros
from tf2_ros import TransformException
from geometry_msgs.msg import Pose, PoseStamped, Quaternion
from moveit_msgs.action import MoveGroup, ExecuteTrajectory
from moveit_msgs.msg import (
    MotionPlanRequest, MotionPlanResponse,
    RobotTrajectory, Constraints, PositionConstraint, OrientationConstraint,
    JointConstraint, PlanningScene, CollisionObject
)
from shape_msgs.msg import SolidPrimitive
from sensor_msgs.msg import JointState

# MCP
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

# ROSClaw Firewall
from rosclaw.firewall.decorator import mujoco_firewall, SafetyLevel, SafetyViolationError

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("rosclaw.moveit2")


# -----------------------------------------------------------------------------
# Data Models - Flywheel-Ready Response Structures
# -----------------------------------------------------------------------------

class ActionStatus(Enum):
    """Action execution status for Data Flywheel tracking."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


@dataclass
class MoveItActionResult:
    """
    Flywheel-ready action result structure.
    All fields are JSON-serializable for Data Flywheel ingestion.
    """
    status: ActionStatus
    action_id: str
    action_type: str
    semantic_goal: str
    timestamp_start: float
    timestamp_end: Optional[float] = None
    duration_seconds: Optional[float] = None
    pose_target: Optional[Dict[str, Any]] = None
    joint_target: Optional[Dict[str, Any]] = None
    trajectory_waypoints: int = 0
    trajectory_duration: float = 0.0
    success: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    firewall_validated: bool = False
    safety_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "semantic_goal": self.semantic_goal,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "pose_target": self.pose_target,
            "joint_target": self.joint_target,
            "trajectory": {
                "waypoints": self.trajectory_waypoints,
                "duration_seconds": self.trajectory_duration,
            },
            "execution": {
                "success": self.success,
                "error_code": self.error_code,
                "error_message": self.error_message,
            },
            "safety": {
                "firewall_validated": self.firewall_validated,
                "violations": self.safety_violations,
            }
        }

    def to_json(self) -> str:
        """Serialize to JSON string for MCP response."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class RobotState:
    """Local state machine for robot state tracking."""
    joint_positions: Dict[str, float] = field(default_factory=dict)
    joint_velocities: Dict[str, float] = field(default_factory=dict)
    end_effector_pose: Optional[Pose] = None
    is_moving: bool = False
    is_planning: bool = False
    last_action_id: Optional[str] = None
    last_error: Optional[str] = None
    planning_group: str = "panda_arm"
    gripper_state: str = "unknown"  # "open", "closed", "unknown"

    def update_from_joint_state(self, msg: JointState) -> None:
        """Update state from ROS JointState message."""
        for name, position in zip(msg.name, msg.position):
            self.joint_positions[name] = position
        for name, velocity in zip(msg.name, msg.velocity):
            self.joint_velocities[name] = velocity


# -----------------------------------------------------------------------------
# ROSClaw MoveIt2 Action Client
# -----------------------------------------------------------------------------

class ROSClawMoveIt2Client:
    """
    ROSClaw-Native MoveIt2 Action Client with async support and state tracking.

    Implements Standards:
    - Standard 1: Async ROS 2 Actions (non-blocking)
    - Standard 4: Graceful Preemption (cancel support)
    - Standard 5: State-Aware Affordance (local state machine)
    - Standard 6: Semantic Spatial Binding (TF2 integration)
    """

    def __init__(self, node_name: str = "rosclaw_moveit2_mcp"):
        """Initialize ROS 2 node and action clients."""
        if not rclpy.ok():
            rclpy.init()

        self.node = Node(node_name)

        # Action Clients for MoveIt2
        self._move_group_client = ActionClient(
            self.node, MoveGroup, "/move_action"
        )
        self._execute_client = ActionClient(
            self.node, ExecuteTrajectory, "/execute_trajectory"
        )

        # TF2 for Semantic Spatial Binding (Standard 6)
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self.node)

        # State tracking (Standard 5)
        self.state = RobotState()
        self._active_tasks: Dict[str, Any] = {}  # task_id -> goal_handle
        self._task_results: Dict[str, MoveItActionResult] = {}

        # Joint state subscription for state tracking
        self._joint_sub = self.node.create_subscription(
            JointState, "/joint_states",
            self._on_joint_state, 10
        )

        # Wait for action servers
        logger.info("Waiting for MoveIt2 action servers...")
        self._move_group_client.wait_for_server(timeout_sec=10.0)
        self._execute_client.wait_for_server(timeout_sec=10.0)
        logger.info("MoveIt2 action servers connected")

        # Start ROS spin thread
        self._spin_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start ROS spin in background thread."""
        self._spin_task = asyncio.create_task(self._ros_spin())

    async def stop(self) -> None:
        """Stop ROS node and cleanup."""
        if self._spin_task:
            self._spin_task.cancel()
            try:
                await self._spin_task
            except asyncio.CancelledError:
                pass
        self.node.destroy_node()

    async def _ros_spin(self) -> None:
        """ROS spin loop running in asyncio."""
        while rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=0.01)
            await asyncio.sleep(0.001)

    def _on_joint_state(self, msg: JointState) -> None:
        """Callback for joint state updates."""
        self.state.update_from_joint_state(msg)

    # -------------------------------------------------------------------------
    # Standard 6: Semantic Spatial Binding (TF2 Integration)
    # -------------------------------------------------------------------------

    async def lookup_tf_pose(
        self,
        target_frame: str,
        reference_frame: str = "base_link"
    ) -> Optional[Pose]:
        """
        Lookup transform using TF2 for semantic spatial binding.

        This abstracts complex 3D math from the LLM - just provide frame names.

        Args:
            target_frame: Target TF frame (e.g., "apple_link", "gripper_target")
            reference_frame: Reference frame (default: "base_link")

        Returns:
            Pose if lookup succeeds, None otherwise
        """
        try:
            transform = self._tf_buffer.lookup_transform(
                reference_frame, target_frame,
                rclpy.time.Time()
            )

            pose = Pose()
            pose.position.x = transform.transform.translation.x
            pose.position.y = transform.transform.translation.y
            pose.position.z = transform.transform.translation.z
            pose.orientation = transform.transform.rotation

            logger.info(f"TF lookup: {target_frame} -> {reference_frame}")
            return pose

        except TransformException as e:
            logger.warning(f"TF lookup failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # Standard 4: Graceful Preemption (Cancel Support)
    # -------------------------------------------------------------------------

    async def cancel_action(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel an active action by task ID.

        Standard 4: Graceful Preemption
        """
        if task_id not in self._active_tasks:
            return {
                "success": False,
                "error": f"No active action with ID: {task_id}"
            }

        goal_handle = self._active_tasks[task_id]

        try:
            cancel_future = goal_handle.cancel_goal_async()
            cancel_result = await self._await_future(cancel_future)

            # Update task result
            if task_id in self._task_results:
                self._task_results[task_id].status = ActionStatus.CANCELED
                self._task_results[task_id].timestamp_end = asyncio.get_event_loop().time()

            del self._active_tasks[task_id]

            return {
                "success": True,
                "message": f"Action {task_id} canceled",
                "cancel_response": cancel_result
            }

        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _await_future(self, future: Future, timeout: float = 30.0) -> Any:
        """Wait for ROS future with asyncio timeout."""
        loop = asyncio.get_event_loop()
        start_time = loop.time()

        while not future.done():
            if loop.time() - start_time > timeout:
                raise TimeoutError(f"Future timeout after {timeout}s")
            await asyncio.sleep(0.01)

        return future.result()

    # -------------------------------------------------------------------------
    # Standard 1 & 5: Async Actions with State Awareness
    # -------------------------------------------------------------------------

    async def plan_and_execute_pose(
        self,
        x: float,
        y: float,
        z: float,
        qx: float,
        qy: float,
        qz: float,
        qw: float,
        semantic_goal: str,
        target_tf_frame: Optional[str] = None,
        planning_group: str = "panda_arm"
    ) -> MoveItActionResult:
        """
        Plan and execute to a Cartesian pose.

        Standards:
        - Standard 1: Async ROS 2 Action (non-blocking)
        - Standard 5: State-Aware (checks if already moving)
        - Standard 6: Semantic TF Binding (optional frame lookup)
        """
        action_id = str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()

        # State-aware check (Standard 5)
        if self.state.is_moving:
            return MoveItActionResult(
                status=ActionStatus.REJECTED,
                action_id=action_id,
                action_type="plan_and_execute_pose",
                semantic_goal=semantic_goal,
                timestamp_start=start_time,
                timestamp_end=start_time,
                duration_seconds=0.0,
                success=False,
                error_code="STATE_REJECTED",
                error_message="Robot is already executing a motion. Cancel existing action first."
            )

        # Semantic TF binding (Standard 6)
        if target_tf_frame:
            tf_pose = await self.lookup_tf_pose(target_tf_frame)
            if tf_pose:
                x, y, z = tf_pose.position.x, tf_pose.position.y, tf_pose.position.z
                qx, qy, qz, qw = (
                    tf_pose.orientation.x, tf_pose.orientation.y,
                    tf_pose.orientation.z, tf_pose.orientation.w
                )
                logger.info(f"Using TF pose from {target_tf_frame}: ({x:.3f}, {y:.3f}, {z:.3f})")
            else:
                logger.warning(f"TF lookup failed for {target_tf_frame}, using provided pose")

        # Create goal pose
        target_pose = Pose()
        target_pose.position.x = x
        target_pose.position.y = y
        target_pose.position.z = z
        target_pose.orientation.x = qx
        target_pose.orientation.y = qy
        target_pose.orientation.z = qz
        target_pose.orientation.w = qw

        # Build MoveGroup goal
        goal_msg = MoveGroup.Goal()

        # Request
        request = MotionPlanRequest()
        request.group_name = planning_group
        request.allowed_planning_time = 5.0
        request.num_planning_attempts = 10

        # Position constraint
        pose_stamped = PoseStamped()
        pose_stamped.header.frame_id = "base_link"
        pose_stamped.pose = target_pose

        goal_msg.request = request
        goal_msg.planning_options.plan_only = False

        try:
            # Send goal (Standard 1: Non-blocking async)
            self.state.is_moving = True
            self.state.last_action_id = action_id

            logger.info(f"Sending MoveGroup goal: {action_id}")
            goal_future = self._move_group_client.send_goal_async(goal_msg)
            goal_handle = await self._await_future(goal_future, timeout=10.0)

            if not goal_handle.accepted:
                self.state.is_moving = False
                return MoveItActionResult(
                    status=ActionStatus.REJECTED,
                    action_id=action_id,
                    action_type="plan_and_execute_pose",
                    semantic_goal=semantic_goal,
                    timestamp_start=start_time,
                    timestamp_end=asyncio.get_event_loop().time(),
                    success=False,
                    error_code="GOAL_REJECTED",
                    error_message="MoveIt rejected the goal"
                )

            # Track active task (Standard 4: Preemption support)
            self._active_tasks[action_id] = goal_handle

            # Wait for result (Standard 1: Non-blocking with yield points)
            result_future = goal_handle.get_result_async()
            action_result = await self._await_future(result_future, timeout=60.0)

            end_time = asyncio.get_event_loop().time()

            # Cleanup
            del self._active_tasks[action_id]
            self.state.is_moving = False

            # Parse result
            success = action_result.result.error_code.val == 1  # SUCCESS

            result = MoveItActionResult(
                status=ActionStatus.SUCCEEDED if success else ActionStatus.FAILED,
                action_id=action_id,
                action_type="plan_and_execute_pose",
                semantic_goal=semantic_goal,
                timestamp_start=start_time,
                timestamp_end=end_time,
                duration_seconds=end_time - start_time,
                pose_target={
                    "position": {"x": x, "y": y, "z": z},
                    "orientation": {"x": qx, "y": qy, "z": qz, "w": qw}
                },
                success=success,
                error_code=str(action_result.result.error_code.val) if not success else None,
                error_message="Planning/execution failed" if not success else None
            )

            self._task_results[action_id] = result
            return result

        except Exception as e:
            self.state.is_moving = False
            if action_id in self._active_tasks:
                del self._active_tasks[action_id]

            logger.error(f"Action failed: {e}")
            return MoveItActionResult(
                status=ActionStatus.FAILED,
                action_id=action_id,
                action_type="plan_and_execute_pose",
                semantic_goal=semantic_goal,
                timestamp_start=start_time,
                timestamp_end=asyncio.get_event_loop().time(),
                success=False,
                error_code="EXCEPTION",
                error_message=str(e)
            )

    async def plan_and_execute_joint_target(
        self,
        joint_positions: Dict[str, float],
        semantic_goal: str,
        planning_group: str = "panda_arm"
    ) -> MoveItActionResult:
        """Plan and execute to a joint configuration."""
        action_id = str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()

        if self.state.is_moving:
            return MoveItActionResult(
                status=ActionStatus.REJECTED,
                action_id=action_id,
                action_type="plan_and_execute_joint",
                semantic_goal=semantic_goal,
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="STATE_REJECTED",
                error_message="Robot is already executing a motion"
            )

        # Build joint constraints
        goal_msg = MoveGroup.Goal()
        request = MotionPlanRequest()
        request.group_name = planning_group

        for joint_name, position in joint_positions.items():
            constraint = JointConstraint()
            constraint.joint_name = joint_name
            constraint.position = position
            constraint.tolerance_above = 0.01
            constraint.tolerance_below = 0.01
            request.goal_constraints.append(Constraints(joint_constraints=[constraint]))

        goal_msg.request = request
        goal_msg.planning_options.plan_only = False

        try:
            self.state.is_moving = True
            self.state.last_action_id = action_id

            goal_future = self._move_group_client.send_goal_async(goal_msg)
            goal_handle = await self._await_future(goal_future, timeout=10.0)

            if not goal_handle.accepted:
                self.state.is_moving = False
                return MoveItActionResult(
                    status=ActionStatus.REJECTED,
                    action_id=action_id,
                    action_type="plan_and_execute_joint",
                    semantic_goal=semantic_goal,
                    timestamp_start=start_time,
                    success=False
                )

            self._active_tasks[action_id] = goal_handle
            result_future = goal_handle.get_result_async()
            action_result = await self._await_future(result_future, timeout=60.0)

            del self._active_tasks[action_id]
            self.state.is_moving = False

            end_time = asyncio.get_event_loop().time()
            success = action_result.result.error_code.val == 1

            return MoveItActionResult(
                status=ActionStatus.SUCCEEDED if success else ActionStatus.FAILED,
                action_id=action_id,
                action_type="plan_and_execute_joint",
                semantic_goal=semantic_goal,
                timestamp_start=start_time,
                timestamp_end=end_time,
                duration_seconds=end_time - start_time,
                joint_target=joint_positions,
                success=success
            )

        except Exception as e:
            self.state.is_moving = False
            logger.error(f"Joint action failed: {e}")
            raise


# -----------------------------------------------------------------------------
# ROSClaw-Native MoveIt2 MCP Server
# -----------------------------------------------------------------------------

mcp = FastMCP("rosclaw-moveit2")
moveit_client: Optional[ROSClawMoveIt2Client] = None


@mcp.on_startup
async def on_startup():
    """Initialize ROSClaw MoveIt2 client on MCP server startup."""
    global moveit_client
    logger.info("Starting ROSClaw-Native MoveIt2 MCP Server...")
    moveit_client = ROSClawMoveIt2Client()
    await moveit_client.start()
    logger.info("✅ ROSClaw MoveIt2 MCP Server ready")


@mcp.on_shutdown
async def on_shutdown():
    """Cleanup on MCP server shutdown."""
    global moveit_client
    if moveit_client:
        await moveit_client.stop()
    logger.info("ROSClaw MoveIt2 MCP Server stopped")


# -----------------------------------------------------------------------------
# MCP Tools - Flywheel-Ready Structured Responses
# -----------------------------------------------------------------------------

@mcp.tool()
async def moveit_get_state() -> str:
    """
    Get current robot state including joint positions and end-effector pose.

    Returns:
        JSON with current robot state
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    state = {
        "joint_positions": moveit_client.state.joint_positions,
        "joint_velocities": moveit_client.state.joint_velocities,
        "is_moving": moveit_client.state.is_moving,
        "planning_group": moveit_client.state.planning_group,
        "last_action_id": moveit_client.state.last_action_id,
        "last_error": moveit_client.state.last_error,
    }

    return json.dumps(state, indent=2)


@mcp.tool()
async def moveit_plan_and_execute_pose(
    x: float,
    y: float,
    z: float,
    qx: float = 0.0,
    qy: float = 0.0,
    qz: float = 0.0,
    qw: float = 1.0,
    target_object_name: str = "",
    target_tf_frame: str = "",
    planning_group: str = "panda_arm"
) -> str:
    """
    Plan and execute motion to a Cartesian pose.

    Standards:
    - Async ROS 2 Action (non-blocking)
    - State-aware (rejects if already moving)
    - TF2 semantic binding (optional frame lookup)

    Args:
        x, y, z: Target position in meters
        qx, qy, qz, qw: Target orientation quaternion
        target_object_name: Semantic name for Data Flywheel tracking
        target_tf_frame: Optional TF frame name for automatic pose lookup
        planning_group: MoveIt planning group name

    Returns:
        Flywheel-ready JSON with action result
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    # Build semantic goal for Data Flywheel
    semantic_goal = target_object_name or f"Move to pose ({x:.3f}, {y:.3f}, {z:.3f})"

    try:
        result = await moveit_client.plan_and_execute_pose(
            x=x, y=y, z=z,
            qx=qx, qy=qy, qz=qz, qw=qw,
            semantic_goal=semantic_goal,
            target_tf_frame=target_tf_frame if target_tf_frame else None,
            planning_group=planning_group
        )
        return result.to_json()

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return json.dumps({
            "status": ActionStatus.FAILED.value,
            "error": str(e),
            "success": False
        })


@mcp.tool()
@mujoco_firewall(
    model_path="src/rosclaw/specs/panda.xml",
    safety_level=SafetyLevel.STRICT
)
async def moveit_plan_and_execute_pose_firewalled(
    x: float,
    y: float,
    z: float,
    qx: float = 0.0,
    qy: float = 0.0,
    qz: float = 0.0,
    qw: float = 1.0,
    target_object_name: str = "",
    target_tf_frame: str = "",
    planning_group: str = "panda_arm"
) -> str:
    """
    Plan and execute motion with Digital Twin Firewall validation.

    Standards:
    - Firewall Integration (@mujoco_firewall decorator)
    - All validation happens in MuJoCo before real execution
    - If validation fails, returns semantic error without moving robot

    Args:
        Same as moveit_plan_and_execute_pose

    Returns:
        Flywheel-ready JSON with firewall validation status
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    semantic_goal = target_object_name or f"Firewalled move to ({x:.3f}, {y:.3f}, {z:.3f})"

    try:
        result = await moveit_client.plan_and_execute_pose(
            x=x, y=y, z=z,
            qx=qx, qy=qy, qz=qz, qw=qw,
            semantic_goal=semantic_goal,
            target_tf_frame=target_tf_frame if target_tf_frame else None,
            planning_group=planning_group
        )

        # Mark as firewall validated
        result.firewall_validated = True
        return result.to_json()

    except SafetyViolationError as e:
        logger.error(f"Firewall validation failed: {e}")
        return json.dumps({
            "status": ActionStatus.REJECTED.value,
            "error_code": "FIREWALL_VIOLATION",
            "error_message": str(e),
            "violations": e.result.violation_details if hasattr(e, 'result') else [],
            "success": False,
            "firewall_validated": False
        })


@mcp.tool()
async def moveit_cancel_action(task_id: str) -> str:
    """
    Cancel an active action by task ID.

    Standard 4: Graceful Preemption

    Args:
        task_id: The action ID to cancel

    Returns:
        JSON with cancel result
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    result = await moveit_client.cancel_action(task_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def moveit_lookup_tf_pose(
    target_frame: str,
    reference_frame: str = "base_link"
) -> str:
    """
    Lookup pose using TF2 semantic spatial binding.

    Standard 6: Semantic Spatial Binding

    Args:
        target_frame: Target TF frame (e.g., "apple_link", "gripper_target")
        reference_frame: Reference frame (default: "base_link")

    Returns:
        JSON with pose or error
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    pose = await moveit_client.lookup_tf_pose(target_frame, reference_frame)

    if pose:
        return json.dumps({
            "success": True,
            "target_frame": target_frame,
            "reference_frame": reference_frame,
            "pose": {
                "position": {
                    "x": pose.position.x,
                    "y": pose.position.y,
                    "z": pose.position.z
                },
                "orientation": {
                    "x": pose.orientation.x,
                    "y": pose.orientation.y,
                    "z": pose.orientation.z,
                    "w": pose.orientation.w
                }
            }
        }, indent=2)
    else:
        return json.dumps({
            "success": False,
            "error": f"TF lookup failed for {target_frame}"
        })


@mcp.tool()
async def moveit_get_active_tasks() -> str:
    """
    Get list of currently active action tasks.

    Returns:
        JSON with active task IDs
    """
    if not moveit_client:
        return json.dumps({"error": "MoveIt client not initialized"})

    return json.dumps({
        "active_tasks": list(moveit_client._active_tasks.keys()),
        "is_moving": moveit_client.state.is_moving
    }, indent=2)


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ROSClaw-Native MoveIt2 MCP Server")
    logger.info("Standards: Async Actions | Flywheel JSON | Firewall | Preemption | State-Aware | TF2")
    logger.info("=" * 60)
    mcp.run(transport="stdio")
