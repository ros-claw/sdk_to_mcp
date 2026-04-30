#!/usr/bin/env python3
"""
ROSClaw-Native Nav2 MCP Server

Production-grade MCP server for Nav2 autonomous navigation with ROSClaw OS integration.

ROSClaw-Native Standards Implemented:
1. Asynchronous ROS 2 Actions - Non-blocking action clients with async/await
2. Flywheel-Ready Responses - Structured JSON for Data Flywheel ingestion
3. Firewall Integration - @mujoco_firewall decorator for simulation validation
4. Graceful Preemption - Active task tracking with cancel_action() support
5. State-Aware Affordance - Local state machine prevents invalid operations
6. Semantic Spatial Binding - TF2 integration for semantic navigation targets

Author: ROSClaw OS Architect
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ROS 2
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.task import Future
import tf2_ros
from tf2_ros import TransformException
from geometry_msgs.msg import Pose, PoseStamped, Quaternion, TransformStamped
from nav2_msgs.action import NavigateToPose, NavigateThroughPoses, FollowWaypoints
from nav2_msgs.msg import BehaviorTreeNavigatorResult
from nav2_simple_commander.robot_navigator import TaskResult

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
logger = logging.getLogger("rosclaw.nav2")


# -----------------------------------------------------------------------------
# Data Models - Flywheel-Ready Response Structures
# -----------------------------------------------------------------------------

class NavigationStatus(Enum):
    """Navigation execution status for Data Flywheel tracking."""
    PENDING = "PENDING"
    NAVIGATING = "NAVIGATING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    RECOVERING = "RECOVERING"


class NavigationMode(Enum):
    """Navigation mode for different behaviors."""
    POSE = "POSE"
    WAYPOINTS = "WAYPOINTS"
    DOCK = "DOCK"


@dataclass
class Nav2ActionResult:
    """
    Flywheel-ready navigation result structure.
    All fields are JSON-serializable for Data Flywheel ingestion.
    """
    status: NavigationStatus
    action_id: str
    action_type: str
    semantic_goal: str
    timestamp_start: float
    timestamp_end: Optional[float] = None
    duration_seconds: Optional[float] = None
    start_pose: Optional[Dict[str, Any]] = None
    goal_pose: Optional[Dict[str, Any]] = None
    waypoints_count: int = 0
    path_length_estimate: float = 0.0
    success: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    recovery_attempts: int = 0
    final_distance_to_goal: float = 0.0
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
            "start_pose": self.start_pose,
            "goal_pose": self.goal_pose,
            "path": {
                "waypoints": self.waypoints_count,
                "estimated_length_meters": self.path_length_estimate,
            },
            "execution": {
                "success": self.success,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "recovery_attempts": self.recovery_attempts,
                "final_distance_to_goal_m": self.final_distance_to_goal,
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
class NavigationState:
    """Local state machine for navigation state tracking."""
    current_pose: Optional[Pose] = None
    goal_pose: Optional[Pose] = None
    is_navigating: bool = False
    is_docked: bool = False
    battery_level: float = 100.0
    current_map: str = ""
    semantic_location: str = "unknown"
    last_action_id: Optional[str] = None
    last_error: Optional[str] = None
    waypoint_queue: List[Tuple[float, float, float]] = field(default_factory=list)
    navigation_mode: NavigationMode = NavigationMode.POSE

    def update_from_pose_stamped(self, msg: PoseStamped) -> None:
        """Update current pose from PoseStamped message."""
        self.current_pose = msg.pose


# -----------------------------------------------------------------------------
# ROSClaw Nav2 Action Client
# -----------------------------------------------------------------------------

class ROSClawNav2Client:
    """
    ROSClaw-Native Nav2 Action Client with async support and state tracking.

    Implements Standards:
    - Standard 1: Async ROS 2 Actions (non-blocking)
    - Standard 4: Graceful Preemption (cancel support)
    - Standard 5: State-Aware Affordance (local state machine)
    - Standard 6: Semantic Spatial Binding (TF2 integration)
    """

    def __init__(self, node_name: str = "rosclaw_nav2_mcp"):
        """Initialize ROS 2 node and action clients."""
        if not rclpy.ok():
            rclpy.init()

        self.node = Node(node_name)

        # Action Clients for Nav2
        self._navigate_to_pose_client = ActionClient(
            self.node, NavigateToPose, "/navigate_to_pose"
        )
        self._navigate_through_poses_client = ActionClient(
            self.node, NavigateThroughPoses, "/navigate_through_poses"
        )
        self._follow_waypoints_client = ActionClient(
            self.node, FollowWaypoints, "/follow_waypoints"
        )

        # TF2 for Semantic Spatial Binding (Standard 6)
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self.node)

        # State tracking (Standard 5)
        self.state = NavigationState()
        self._active_tasks: Dict[str, Any] = {}  # task_id -> goal_handle
        self._task_results: Dict[str, Nav2ActionResult] = {}

        # Current pose subscription for state tracking
        self._pose_sub = self.node.create_subscription(
            PoseStamped, "/amcl_pose",
            self._on_pose_update, 10
        )

        # Wait for action servers
        logger.info("Waiting for Nav2 action servers...")
        self._navigate_to_pose_client.wait_for_server(timeout_sec=10.0)
        self._navigate_through_poses_client.wait_for_server(timeout_sec=5.0)
        self._follow_waypoints_client.wait_for_server(timeout_sec=5.0)
        logger.info("Nav2 action servers connected")

        # Start ROS spin task
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

    def _on_pose_update(self, msg: PoseStamped) -> None:
        """Callback for pose updates."""
        self.state.update_from_pose_stamped(msg)

    # -------------------------------------------------------------------------
    # Standard 6: Semantic Spatial Binding (TF2 Integration)
    # -------------------------------------------------------------------------

    async def lookup_tf_pose(
        self,
        target_frame: str,
        reference_frame: str = "map"
    ) -> Optional[Pose]:
        """
        Lookup transform using TF2 for semantic spatial binding.

        This abstracts complex 2D/3D math from the LLM - just provide semantic frame names.

        Args:
            target_frame: Target TF frame (e.g., "kitchen_table", "charging_dock")
            reference_frame: Reference frame (default: "map")

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

    def create_pose_stamped(
        self,
        x: float,
        y: float,
        theta: float,
        frame_id: str = "map"
    ) -> PoseStamped:
        """
        Create a PoseStamped from 2D coordinates (x, y, theta).

        Args:
            x: X coordinate in meters
            y: Y coordinate in meters
            theta: Orientation in radians (yaw)
            frame_id: TF frame ID

        Returns:
            PoseStamped message
        """
        pose = PoseStamped()
        pose.header.frame_id = frame_id
        pose.header.stamp = self.node.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = 0.0

        # Convert theta (yaw) to quaternion
        pose.pose.orientation.w = math.cos(theta / 2.0)
        pose.pose.orientation.x = 0.0
        pose.pose.orientation.y = 0.0
        pose.pose.orientation.z = math.sin(theta / 2.0)

        return pose

    # -------------------------------------------------------------------------
    # Standard 4: Graceful Preemption (Cancel Support)
    # -------------------------------------------------------------------------

    async def cancel_navigation(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel an active navigation by task ID.

        Standard 4: Graceful Preemption
        """
        if task_id not in self._active_tasks:
            return {
                "success": False,
                "error": f"No active navigation with ID: {task_id}"
            }

        goal_handle = self._active_tasks[task_id]

        try:
            cancel_future = goal_handle.cancel_goal_async()
            cancel_result = await self._await_future(cancel_future)

            # Update task result
            if task_id in self._task_results:
                self._task_results[task_id].status = NavigationStatus.CANCELED
                self._task_results[task_id].timestamp_end = asyncio.get_event_loop().time()

            del self._active_tasks[task_id]
            self.state.is_navigating = False

            return {
                "success": True,
                "message": f"Navigation {task_id} canceled",
                "cancel_response": str(cancel_result)
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

    async def navigate_to_pose(
        self,
        x: float,
        y: float,
        theta: float,
        semantic_label: str,
        target_tf_frame: Optional[str] = None,
        behavior_tree: str = ""
    ) -> Nav2ActionResult:
        """
        Navigate to a specific pose with semantic labeling.

        Standards:
        - Standard 1: Async ROS 2 Action (non-blocking)
        - Standard 5: State-Aware (checks if already navigating)
        - Standard 6: Semantic TF Binding (optional frame lookup)
        """
        action_id = str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()

        # State-aware check (Standard 5)
        if self.state.is_navigating:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="navigate_to_pose",
                semantic_goal=semantic_label or f"Navigate to ({x:.2f}, {y:.2f})",
                timestamp_start=start_time,
                timestamp_end=start_time,
                duration_seconds=0.0,
                success=False,
                error_code="STATE_REJECTED",
                error_message="Robot is already navigating. Cancel existing navigation first."
            )

        # Semantic TF binding (Standard 6)
        if target_tf_frame:
            tf_pose = await self.lookup_tf_pose(target_tf_frame)
            if tf_pose:
                x = tf_pose.position.x
                y = tf_pose.position.y
                # Extract theta from quaternion
                qw = tf_pose.orientation.w
                qz = tf_pose.orientation.z
                theta = 2.0 * math.atan2(qz, qw)
                logger.info(f"Using TF pose from {target_tf_frame}: ({x:.2f}, {y:.2f}, {theta:.2f})")
            else:
                logger.warning(f"TF lookup failed for {target_tf_frame}, using provided pose")

        # Create goal pose
        goal_pose = self.create_pose_stamped(x, y, theta)

        # Record start pose for Data Flywheel
        start_pose_dict = None
        if self.state.current_pose:
            start_pose_dict = {
                "x": self.state.current_pose.position.x,
                "y": self.state.current_pose.position.y,
                "theta": 2.0 * math.atan2(
                    self.state.current_pose.orientation.z,
                    self.state.current_pose.orientation.w
                )
            }

        # Build NavigateToPose goal
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = goal_pose
        if behavior_tree:
            goal_msg.behavior_tree = behavior_tree

        try:
            # Send goal (Standard 1: Non-blocking async)
            self.state.is_navigating = True
            self.state.last_action_id = action_id
            self.state.goal_pose = goal_pose.pose
            self.state.navigation_mode = NavigationMode.POSE

            logger.info(f"Sending NavigateToPose goal: {action_id}")
            goal_future = self._navigate_to_pose_client.send_goal_async(goal_msg)
            goal_handle = await self._await_future(goal_future, timeout=10.0)

            if not goal_handle.accepted:
                self.state.is_navigating = False
                return Nav2ActionResult(
                    status=NavigationStatus.REJECTED,
                    action_id=action_id,
                    action_type="navigate_to_pose",
                    semantic_goal=semantic_label or f"Navigate to ({x:.2f}, {y:.2f})",
                    timestamp_start=start_time,
                    timestamp_end=asyncio.get_event_loop().time(),
                    start_pose=start_pose_dict,
                    goal_pose={"x": x, "y": y, "theta": theta},
                    success=False,
                    error_code="GOAL_REJECTED",
                    error_message="Nav2 rejected the navigation goal"
                )

            # Track active task (Standard 4: Preemption support)
            self._active_tasks[action_id] = goal_handle

            # Wait for result (Standard 1: Non-blocking with yield points)
            result_future = goal_handle.get_result_async()
            action_result = await self._await_future(result_future, timeout=300.0)

            end_time = asyncio.get_event_loop().time()

            # Cleanup
            del self._active_tasks[action_id]
            self.state.is_navigating = False

            # Calculate final distance to goal
            final_distance = 0.0
            if self.state.current_pose:
                dx = self.state.current_pose.position.x - x
                dy = self.state.current_pose.position.y - y
                final_distance = math.sqrt(dx*dx + dy*dy)

            # Parse result
            success = action_result.status == 4  # STATUS_SUCCEEDED = 4

            result = Nav2ActionResult(
                status=NavigationStatus.SUCCEEDED if success else NavigationStatus.FAILED,
                action_id=action_id,
                action_type="navigate_to_pose",
                semantic_goal=semantic_label or f"Navigate to ({x:.2f}, {y:.2f})",
                timestamp_start=start_time,
                timestamp_end=end_time,
                duration_seconds=end_time - start_time,
                start_pose=start_pose_dict,
                goal_pose={"x": x, "y": y, "theta": theta},
                path_length_estimate=math.sqrt((x - (start_pose_dict["x"] if start_pose_dict else 0))**2 +
                                               (y - (start_pose_dict["y"] if start_pose_dict else 0))**2) if start_pose_dict else 0.0,
                success=success,
                error_code=str(action_result.status) if not success else None,
                error_message="Navigation failed" if not success else None,
                final_distance_to_goal=final_distance
            )

            self._task_results[action_id] = result
            return result

        except Exception as e:
            self.state.is_navigating = False
            if action_id in self._active_tasks:
                del self._active_tasks[action_id]

            logger.error(f"Navigation failed: {e}")
            return Nav2ActionResult(
                status=NavigationStatus.FAILED,
                action_id=action_id,
                action_type="navigate_to_pose",
                semantic_goal=semantic_label or f"Navigate to ({x:.2f}, {y:.2f})",
                timestamp_start=start_time,
                timestamp_end=asyncio.get_event_loop().time(),
                start_pose=start_pose_dict,
                goal_pose={"x": x, "y": y, "theta": theta},
                success=False,
                error_code="EXCEPTION",
                error_message=str(e)
            )

    async def navigate_through_waypoints(
        self,
        waypoints: List[Tuple[float, float, float]],
        semantic_label: str
    ) -> Nav2ActionResult:
        """
        Navigate through a sequence of waypoints.

        Args:
            waypoints: List of (x, y, theta) tuples
            semantic_label: Semantic description of the waypoint mission
        """
        action_id = str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()

        # State-aware check
        if self.state.is_navigating:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="navigate_waypoints",
                semantic_goal=semantic_label,
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="STATE_REJECTED",
                error_message="Robot is already navigating. Cancel existing navigation first."
            )

        if len(waypoints) == 0:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="navigate_waypoints",
                semantic_goal=semantic_label,
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="INVALID_WAYPOINTS",
                error_message="No waypoints provided"
            )

        # Convert waypoints to PoseStamped
        pose_goals = []
        for wp in waypoints:
            pose_goals.append(self.create_pose_stamped(wp[0], wp[1], wp[2]))

        # Build FollowWaypoints goal
        goal_msg = FollowWaypoints.Goal()
        goal_msg.poses = pose_goals

        try:
            self.state.is_navigating = True
            self.state.last_action_id = action_id
            self.state.navigation_mode = NavigationMode.WAYPOINTS
            self.state.waypoint_queue = waypoints

            logger.info(f"Sending FollowWaypoints goal: {action_id} ({len(waypoints)} waypoints)")
            goal_future = self._follow_waypoints_client.send_goal_async(goal_msg)
            goal_handle = await self._await_future(goal_future, timeout=10.0)

            if not goal_handle.accepted:
                self.state.is_navigating = False
                return Nav2ActionResult(
                    status=NavigationStatus.REJECTED,
                    action_id=action_id,
                    action_type="navigate_waypoints",
                    semantic_goal=semantic_label,
                    timestamp_start=start_time,
                    success=False,
                    error_code="GOAL_REJECTED",
                    error_message="Nav2 rejected the waypoint goal"
                )

            self._active_tasks[action_id] = goal_handle

            # Wait for result
            result_future = goal_handle.get_result_async()
            action_result = await self._await_future(result_future, timeout=600.0)

            end_time = asyncio.get_event_loop().time()

            del self._active_tasks[action_id]
            self.state.is_navigating = False
            self.state.waypoint_queue = []

            # Calculate path length estimate
            path_length = 0.0
            if len(waypoints) > 1:
                for i in range(1, len(waypoints)):
                    dx = waypoints[i][0] - waypoints[i-1][0]
                    dy = waypoints[i][1] - waypoints[i-1][1]
                    path_length += math.sqrt(dx*dx + dy*dy)

            success = action_result.status == 4

            return Nav2ActionResult(
                status=NavigationStatus.SUCCEEDED if success else NavigationStatus.FAILED,
                action_id=action_id,
                action_type="navigate_waypoints",
                semantic_goal=semantic_label,
                timestamp_start=start_time,
                timestamp_end=end_time,
                duration_seconds=end_time - start_time,
                waypoints_count=len(waypoints),
                path_length_estimate=path_length,
                success=success,
                error_code=str(action_result.status) if not success else None,
                error_message="Waypoint navigation failed" if not success else None
            )

        except Exception as e:
            self.state.is_navigating = False
            self.state.waypoint_queue = []
            if action_id in self._active_tasks:
                del self._active_tasks[action_id]

            logger.error(f"Waypoint navigation failed: {e}")
            raise

    async def dock_robot(
        self,
        dock_pose: Optional[Tuple[float, float, float]] = None,
        dock_tf_frame: Optional[str] = None,
        dock_id: str = ""
    ) -> Nav2ActionResult:
        """
        Dock the robot to a charging station.

        Args:
            dock_pose: Optional (x, y, theta) of dock
            dock_tf_frame: Optional TF frame name for dock
            dock_id: Optional dock identifier
        """
        action_id = str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()

        # State-aware check
        if self.state.is_navigating:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="dock",
                semantic_goal=f"Dock to {dock_id or dock_tf_frame or 'charging station'}",
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="STATE_REJECTED",
                error_message="Robot is already navigating"
            )

        if self.state.is_docked:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="dock",
                semantic_goal=f"Dock to {dock_id or dock_tf_frame or 'charging station'}",
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="ALREADY_DOCKED",
                error_message="Robot is already docked"
            )

        # Use TF frame if provided
        if dock_tf_frame:
            tf_pose = await self.lookup_tf_pose(dock_tf_frame)
            if tf_pose:
                x = tf_pose.position.x
                y = tf_pose.position.y
                qw = tf_pose.orientation.w
                qz = tf_pose.orientation.z
                theta = 2.0 * math.atan2(qz, qw)
                dock_pose = (x, y, theta)
            else:
                return Nav2ActionResult(
                    status=NavigationStatus.FAILED,
                    action_id=action_id,
                    action_type="dock",
                    semantic_goal=f"Dock to {dock_tf_frame}",
                    timestamp_start=start_time,
                    timestamp_end=start_time,
                    success=False,
                    error_code="TF_LOOKUP_FAILED",
                    error_message=f"Could not find TF frame: {dock_tf_frame}"
                )

        if not dock_pose:
            return Nav2ActionResult(
                status=NavigationStatus.REJECTED,
                action_id=action_id,
                action_type="dock",
                semantic_goal="Dock to charging station",
                timestamp_start=start_time,
                timestamp_end=start_time,
                success=False,
                error_code="MISSING_DOCK_INFO",
                error_message="Must provide dock_pose, dock_tf_frame, or dock_id"
            )

        # Navigate to dock pose first
        semantic_goal = f"Dock to {dock_id or 'charging station'}"
        result = await self.navigate_to_pose(
            x=dock_pose[0],
            y=dock_pose[1],
            theta=dock_pose[2],
            semantic_label=semantic_goal
        )

        if result.success:
            self.state.is_docked = True
            result.action_type = "dock"

        return result


# -----------------------------------------------------------------------------
# ROSClaw-Native Nav2 MCP Server
# -----------------------------------------------------------------------------

mcp = FastMCP("rosclaw-nav2")
nav2_client: Optional[ROSClawNav2Client] = None


@mcp.on_startup
async def on_startup():
    """Initialize ROSClaw Nav2 client on MCP server startup."""
    global nav2_client
    logger.info("Starting ROSClaw-Native Nav2 MCP Server...")
    nav2_client = ROSClawNav2Client()
    await nav2_client.start()
    logger.info("ROSClaw Nav2 MCP Server ready")


@mcp.on_shutdown
async def on_shutdown():
    """Cleanup on MCP server shutdown."""
    global nav2_client
    if nav2_client:
        await nav2_client.stop()
    logger.info("ROSClaw Nav2 MCP Server stopped")


# -----------------------------------------------------------------------------
# MCP Tools - Flywheel-Ready Structured Responses
# -----------------------------------------------------------------------------

@mcp.tool()
async def nav2_get_state() -> str:
    """
    Get current navigation state including pose and navigation status.

    Returns:
        JSON with current navigation state
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    state = nav2_client.state
    current_pose = None
    if state.current_pose:
        current_pose = {
            "x": state.current_pose.position.x,
            "y": state.current_pose.position.y,
            "theta": 2.0 * math.atan2(
                state.current_pose.orientation.z,
                state.current_pose.orientation.w
            )
        }

    goal_pose = None
    if state.goal_pose:
        goal_pose = {
            "x": state.goal_pose.position.x,
            "y": state.goal_pose.position.y,
            "theta": 2.0 * math.atan2(
                state.goal_pose.orientation.z,
                state.goal_pose.orientation.w
            )
        }

    return json.dumps({
        "current_pose": current_pose,
        "goal_pose": goal_pose,
        "is_navigating": state.is_navigating,
        "is_docked": state.is_docked,
        "battery_level": state.battery_level,
        "semantic_location": state.semantic_location,
        "navigation_mode": state.navigation_mode.value,
        "last_action_id": state.last_action_id,
        "last_error": state.last_error,
        "waypoint_queue_length": len(state.waypoint_queue)
    }, indent=2)


@mcp.tool()
async def nav2_navigate_to_pose(
    x: float,
    y: float,
    theta: float = 0.0,
    semantic_label: str = "",
    target_tf_frame: str = ""
) -> str:
    """
    Navigate to a specific pose with optional semantic labeling.

    Standards:
    - Async ROS 2 Action (non-blocking)
    - State-aware (rejects if already navigating)
    - TF2 semantic binding (optional frame lookup)

    Args:
        x: X coordinate in meters (map frame)
        y: Y coordinate in meters (map frame)
        theta: Target orientation in radians (yaw)
        semantic_label: Semantic description for Data Flywheel (e.g., "kitchen", "office")
        target_tf_frame: Optional TF frame name for automatic pose lookup (e.g., "kitchen_table")

    Returns:
        Flywheel-ready JSON with navigation result
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    semantic_goal = semantic_label or f"Navigate to ({x:.2f}, {y:.2f})"

    try:
        result = await nav2_client.navigate_to_pose(
            x=x, y=y, theta=theta,
            semantic_label=semantic_goal,
            target_tf_frame=target_tf_frame if target_tf_frame else None
        )
        return result.to_json()

    except Exception as e:
        logger.error(f"Navigation tool failed: {e}")
        return json.dumps({
            "status": NavigationStatus.FAILED.value,
            "error": str(e),
            "success": False
        })


@mcp.tool()
@mujoco_firewall(
    model_path="src/rosclaw/specs/nav2_sim.xml",
    safety_level=SafetyLevel.MODERATE
)
async def nav2_navigate_to_pose_firewalled(
    x: float,
    y: float,
    theta: float = 0.0,
    semantic_label: str = "",
    target_tf_frame: str = ""
) -> str:
    """
    Navigate to pose with Digital Twin Firewall validation.

    Standards:
    - Firewall Integration (@mujoco_firewall decorator)
    - Path validation in simulation before real execution
    - If validation fails, returns semantic error without moving robot

    Args:
        Same as nav2_navigate_to_pose

    Returns:
        Flywheel-ready JSON with firewall validation status
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    semantic_goal = semantic_label or f"Firewalled navigate to ({x:.2f}, {y:.2f})"

    try:
        result = await nav2_client.navigate_to_pose(
            x=x, y=y, theta=theta,
            semantic_label=semantic_goal,
            target_tf_frame=target_tf_frame if target_tf_frame else None
        )

        # Mark as firewall validated
        result.firewall_validated = True
        return result.to_json()

    except SafetyViolationError as e:
        logger.error(f"Firewall validation failed: {e}")
        return json.dumps({
            "status": NavigationStatus.REJECTED.value,
            "error_code": "FIREWALL_VIOLATION",
            "error_message": str(e),
            "violations": e.result.violation_details if hasattr(e, 'result') else [],
            "success": False,
            "firewall_validated": False
        })


@mcp.tool()
async def nav2_navigate_through_waypoints(
    waypoints_json: str,
    semantic_label: str = ""
) -> str:
    """
    Navigate through a sequence of waypoints.

    Args:
        waypoints_json: JSON array of [x, y, theta] waypoints
            Example: "[[1.0, 2.0, 0.0], [3.0, 4.0, 1.57]]"
        semantic_label: Semantic description of the waypoint mission

    Returns:
        Flywheel-ready JSON with navigation result
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    try:
        waypoints = json.loads(waypoints_json)
        if not isinstance(waypoints, list):
            return json.dumps({
                "error": "waypoints_json must be a JSON array",
                "success": False
            })

        # Validate waypoint format
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, (list, tuple)) or len(wp) not in [2, 3]:
                return json.dumps({
                    "error": f"Waypoint {i} must be [x, y] or [x, y, theta]",
                    "success": False
                })
            # Add default theta if missing
            if len(wp) == 2:
                waypoints[i] = [wp[0], wp[1], 0.0]

        semantic_goal = semantic_label or f"Waypoint mission ({len(waypoints)} points)"

        result = await nav2_client.navigate_through_waypoints(
            waypoints=waypoints,
            semantic_label=semantic_goal
        )
        return result.to_json()

    except json.JSONDecodeError as e:
        return json.dumps({
            "error": f"Invalid JSON: {str(e)}",
            "success": False
        })
    except Exception as e:
        logger.error(f"Waypoint navigation failed: {e}")
        return json.dumps({
            "status": NavigationStatus.FAILED.value,
            "error": str(e),
            "success": False
        })


@mcp.tool()
async def nav2_cancel_navigation(task_id: str) -> str:
    """
    Cancel an active navigation by task ID.

    Standard 4: Graceful Preemption

    Args:
        task_id: The navigation action ID to cancel

    Returns:
        JSON with cancel result
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    result = await nav2_client.cancel_navigation(task_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def nav2_lookup_tf_pose(
    target_frame: str,
    reference_frame: str = "map"
) -> str:
    """
    Lookup pose using TF2 semantic spatial binding.

    Standard 6: Semantic Spatial Binding

    Args:
        target_frame: Target TF frame (e.g., "kitchen_table", "charging_dock")
        reference_frame: Reference frame (default: "map")

    Returns:
        JSON with pose (x, y, theta) or error
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    pose = await nav2_client.lookup_tf_pose(target_frame, reference_frame)

    if pose:
        # Convert quaternion to theta (yaw)
        qw = pose.orientation.w
        qz = pose.orientation.z
        theta = 2.0 * math.atan2(qz, qw)

        return json.dumps({
            "success": True,
            "target_frame": target_frame,
            "reference_frame": reference_frame,
            "pose": {
                "x": pose.position.x,
                "y": pose.position.y,
                "theta": theta
            }
        }, indent=2)
    else:
        return json.dumps({
            "success": False,
            "error": f"TF lookup failed for {target_frame}"
        })


@mcp.tool()
async def nav2_get_active_navigations() -> str:
    """
    Get list of currently active navigation tasks.

    Returns:
        JSON with active task IDs and navigation status
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    return json.dumps({
        "active_tasks": list(nav2_client._active_tasks.keys()),
        "is_navigating": nav2_client.state.is_navigating,
        "current_mode": nav2_client.state.navigation_mode.value
    }, indent=2)


@mcp.tool()
async def nav2_dock_robot(
    x: float = 0.0,
    y: float = 0.0,
    theta: float = 0.0,
    dock_tf_frame: str = "",
    dock_id: str = ""
) -> str:
    """
    Dock the robot to a charging station.

    Args:
        x: X coordinate of dock (if not using TF frame)
        y: Y coordinate of dock (if not using TF frame)
        theta: Orientation of dock approach (if not using TF frame)
        dock_tf_frame: Optional TF frame name for automatic dock lookup
        dock_id: Optional dock identifier for Data Flywheel

    Returns:
        Flywheel-ready JSON with docking result
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    try:
        dock_pose = None
        if not dock_tf_frame and (x != 0.0 or y != 0.0):
            dock_pose = (x, y, theta)

        result = await nav2_client.dock_robot(
            dock_pose=dock_pose,
            dock_tf_frame=dock_tf_frame if dock_tf_frame else None,
            dock_id=dock_id
        )
        return result.to_json()

    except Exception as e:
        logger.error(f"Docking failed: {e}")
        return json.dumps({
            "status": NavigationStatus.FAILED.value,
            "error": str(e),
            "success": False
        })


@mcp.tool()
async def nav2_set_semantic_location(location: str) -> str:
    """
    Set the current semantic location for Data Flywheel tracking.

    Args:
        location: Semantic location name (e.g., "kitchen", "office", "hallway")

    Returns:
        Confirmation JSON
    """
    if not nav2_client:
        return json.dumps({"error": "Nav2 client not initialized"})

    nav2_client.state.semantic_location = location
    return json.dumps({
        "success": True,
        "semantic_location": location,
        "message": f"Semantic location set to: {location}"
    })


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ROSClaw-Native Nav2 MCP Server")
    logger.info("Standards: Async Actions | Flywheel JSON | Firewall | Preemption | State-Aware | TF2")
    logger.info("=" * 60)
    mcp.run(transport="stdio")
