#!/usr/bin/env python3
"""
🔄 Self-Healing Code Generator V2.0 - Agentic Asset Bundle Compiler

SDK-to-MCP V2.0 的核心引擎。
集成 The Critic Agent 的三阶段智能体工作流：
1. The Ingestor (摄取者) - 解析硬件上下文
2. The Generator (生成器) - 生成 MCP Server 代码
3. The Critic (审查官) - 验证 6 大 ROSClaw-Native 标准

This is not just code generation. This is ROSClaw-Native Architecture Enforcement.
"""

from __future__ import annotations

import os
import re
import sys
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import Critic Agent
from critic_agent import CriticAgent, CriticReport, the_critic


@dataclass
class AgenticContext:
    """
    智能体工作流上下文

    贯穿 Ingestor -> Generator -> Critic 的共享上下文
    """
    # 输入
    robot_name: str = ""
    vendor: str = ""
    robot_type: str = ""  # arm, mobile, humanoid, drone
    sdk_docs: str = ""  # 原始 SDK 文档内容
    ros2_interfaces: List[Dict[str, Any]] = field(default_factory=list)

    # Ingestor 输出
    hardware_context: Dict[str, Any] = field(default_factory=dict)
    action_semantics: Dict[str, Any] = field(default_factory=dict)
    safety_constraints: Dict[str, Any] = field(default_factory=dict)

    # Generator 输出
    mcp_code: str = ""

    # Critic 输出
    critic_report: Optional[CriticReport] = None

    # 迭代状态
    attempt_number: int = 0
    max_retries: int = 5

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典用于 LLM 上下文"""
        return {
            "robot": {
                "name": self.robot_name,
                "vendor": self.vendor,
                "type": self.robot_type,
            },
            "hardware_context": self.hardware_context,
            "action_semantics": self.action_semantics,
            "safety_constraints": self.safety_constraints,
            "ros2_interfaces": self.ros2_interfaces,
        }


@dataclass
class AgenticResult:
    """Agentic Workflow 最终结果"""
    success: bool
    context: AgenticContext
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    output_dir: Optional[str] = None

    def get_summary(self) -> str:
        """获取人类可读的摘要"""
        lines = [
            "=" * 60,
            "🎭 AGENTIC COMPILER RESULT",
            "=" * 60,
            f"\nStatus: {'✅ SUCCESS' if self.success else '❌ FAILED'}",
            f"Robot: {self.context.robot_name} ({self.context.vendor})",
            f"Total Attempts: {len(self.attempts)}",
        ]

        if self.output_dir:
            lines.append(f"Output: {self.output_dir}")

        if self.attempts:
            lines.append("\n📊 Attempt History:")
            for i, attempt in enumerate(self.attempts, 1):
                status = "✅" if attempt.get("passed") else "❌"
                lines.append(f"  {status} Attempt {i}: {attempt.get('message', 'N/A')}")

        lines.append("=" * 60)
        return "\n".join(lines)


class TheIngestor:
    """
    第一阶段：摄取者 Agent

    解析异构数据（PDF, C++, ROS 2 interface），提取硬件上下文。
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def ingest(self, context: AgenticContext) -> AgenticContext:
        """
        摄取并解析硬件上下文

        从 SDK 文档中提取：
        - 动作语义 (哪些动作需要防火墙？)
        - 安全约束 (速度/位置限制)
        - ROS 2 接口类型 (Action/Service/Topic)
        """
        print(f"\n[INGESTOR] 📥 Ingesting {context.robot_name} SDK documentation...")

        # 分析 ROS 2 接口
        context.ros2_interfaces = self._extract_ros2_interfaces(context.sdk_docs)

        # 提取动作语义
        context.action_semantics = self._analyze_action_semantics(
            context.ros2_interfaces
        )

        # 提取安全约束
        context.safety_constraints = self._extract_safety_constraints(
            context.sdk_docs
        )

        # 构建硬件上下文
        context.hardware_context = {
            "type": context.robot_type,
            "actions": context.action_semantics,
            "safety": context.safety_constraints,
            "interfaces": context.ros2_interfaces,
        }

        print(f"[INGESTOR] ✅ Extracted {len(context.ros2_interfaces)} ROS 2 interfaces")
        print(f"[INGESTOR] 🔍 Found {len(context.action_semantics.get('physical_actions', []))} physical actions")
        print(f"[INGESTOR] ⚠️  Identified {len(context.safety_constraints.get('limits', {}))} safety constraints")

        return context

    def _extract_ros2_interfaces(self, docs: str) -> List[Dict[str, Any]]:
        """提取 ROS 2 接口定义"""
        interfaces = []

        # 匹配 Action 定义
        action_pattern = r'(\w+)::action::(\w+)'
        for match in re.finditer(action_pattern, docs):
            pkg, name = match.groups()
            interfaces.append({
                "type": "action",
                "package": pkg,
                "name": name,
                "requires_preemption": True,
                "semantic_type": self._infer_semantic_type(name),
            })

        # 匹配 Service 定义
        service_pattern = r'(\w+)::srv::(\w+)'
        for match in re.finditer(service_pattern, docs):
            pkg, name = match.groups()
            interfaces.append({
                "type": "service",
                "package": pkg,
                "name": name,
                "semantic_type": self._infer_semantic_type(name),
            })

        # 匹配 Topic 定义
        topic_pattern = r'topic\s*:\s*["\']([^"\']+)["\']'
        for match in re.finditer(topic_pattern, docs, re.IGNORECASE):
            topic = match.group(1)
            interfaces.append({
                "type": "topic",
                "name": topic,
                "semantic_type": self._infer_semantic_type(topic),
            })

        return interfaces

    def _analyze_action_semantics(self, interfaces: List[Dict]) -> Dict[str, Any]:
        """分析动作语义"""
        physical_actions = []
        query_actions = []

        for iface in interfaces:
            name = iface.get("name", "")
            semantic = self._infer_semantic_type(name)

            if semantic == "physical":
                physical_actions.append({
                    "name": name,
                    "requires_firewall": True,
                    "requires_preemption": iface.get("requires_preemption", False),
                })
            else:
                query_actions.append({
                    "name": name,
                    "requires_firewall": False,
                })

        return {
            "physical_actions": physical_actions,
            "query_actions": query_actions,
        }

    def _extract_safety_constraints(self, docs: str) -> Dict[str, Any]:
        """提取安全约束"""
        limits = {}

        # 尝试提取速度限制
        velocity_pattern = r'velocity.*limit\s*[:=]?\s*(\d+\.?\d*)'
        for match in re.finditer(velocity_pattern, docs, re.IGNORECASE):
            limits["velocity_max"] = float(match.group(1))

        # 尝试提取位置限制
        position_pattern = r'position.*limit\s*[:=]?\s*([-\d\.]+)\s*,?\s*([-\d\.]+)?'
        for match in re.finditer(position_pattern, docs, re.IGNORECASE):
            if match.group(2):
                limits["position_min"] = float(match.group(1))
                limits["position_max"] = float(match.group(2))

        return {
            "limits": limits,
            "collision_avoidance": "collision" in docs.lower(),
        }

    def _infer_semantic_type(self, name: str) -> str:
        """推断语义类型"""
        physical_keywords = [
            "move", "navigate", "grasp", "rotate", "drive", "walk",
            "joint", "position", "velocity", "torque", "execute"
        ]
        query_keywords = ["get", "query", "state", "status", "info"]

        name_lower = name.lower()

        for keyword in physical_keywords:
            if keyword in name_lower:
                return "physical"

        for keyword in query_keywords:
            if keyword in name_lower:
                return "query"

        return "unknown"


class TheGenerator:
    """
    第二阶段：生成器 Agent

    基于摄取的硬件上下文，生成符合 ROSClaw-Native 标准的 MCP Server 代码。
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def generate(self, context: AgenticContext) -> AgenticContext:
        """
        生成 MCP Server 代码

        使用系统提示词 + 黄金范本 + 硬件上下文进行生成
        """
        print(f"\n[GENERATOR] 🛠️  Generating MCP Server for {context.robot_name}...")

        # 加载系统提示词
        system_prompt = self._load_system_prompt()

        # 加载黄金范本
        golden_examples = self._load_golden_examples(context.robot_type)

        # 构建生成提示词
        generation_prompt = self._build_generation_prompt(context)

        # 调用 LLM 生成代码
        if self.llm_client:
            context.mcp_code = self.llm_client.generate(
                system_prompt=system_prompt,
                golden_examples=golden_examples,
                user_prompt=generation_prompt
            )
        else:
            # 模拟生成（用于测试）
            context.mcp_code = self._generate_placeholder_code(context)

        print(f"[GENERATOR] ✅ Generated {len(context.mcp_code)} characters of code")

        return context

    def _load_system_prompt(self) -> str:
        """加载系统提示词"""
        prompt_path = Path(__file__).parent / "templates" / "system_prompt_v2.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "You are a ROSClaw-Native MCP Server generator."

    def _load_golden_examples(self, robot_type: str) -> str:
        """加载黄金范本"""
        golden_dir = Path(__file__).parent / "templates" / "golden"

        examples = []

        # 根据机器人类型选择范本
        if robot_type == "arm":
            golden_file = golden_dir / "moveit2_mcp_golden.py"
        elif robot_type == "mobile":
            golden_file = golden_dir / "nav2_mcp_golden.py"
        else:
            # 默认使用两个范本
            golden_file = golden_dir / "moveit2_mcp_golden.py"

        if golden_file.exists():
            examples.append(f"=== GOLDEN EXAMPLE: {golden_file.name} ===\n")
            examples.append(golden_file.read_text(encoding="utf-8"))

        return "\n\n".join(examples)

    def _build_generation_prompt(self, context: AgenticContext) -> str:
        """构建生成提示词"""
        lines = [
            f"Generate a ROSClaw-Native MCP Server for {context.vendor} {context.robot_name}.",
            "",
            "Hardware Context:",
            json.dumps(context.to_dict(), indent=2, ensure_ascii=False),
            "",
            "Requirements:",
            "1. Implement ALL 6 ROSClaw-Native Standards",
            "2. Use the Golden Templates as your architectural guide",
            "3. Generate ONLY the complete Python code, no explanations",
            "4. Include proper error handling and logging",
            "5. Follow ROS 2 action client patterns exactly as shown in templates",
        ]

        return "\n".join(lines)

    def _generate_placeholder_code(self, context: AgenticContext) -> str:
        """生成占位代码（用于测试）"""
        robot_class = "".join(word.capitalize() for word in context.robot_name.split("_"))

        return f'''#!/usr/bin/env python3
"""ROSClaw-Native MCP Server for {context.robot_name} - GENERATED"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.task import Future
import tf2_ros
from geometry_msgs.msg import Pose, PoseStamped
from mcp.server.fastmcp import FastMCP
from rosclaw.firewall.decorator import mujoco_firewall, SafetyLevel, SafetyViolationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rosclaw.{context.robot_name}")

class ActionStatus(Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

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
        return json.dumps({{
            "status": self.status.value,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "semantic_goal": self.semantic_goal,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error": {{"code": self.error_code, "message": self.error_message}},
            "safety": {{"firewall_validated": self.firewall_validated, "violations": self.safety_violations}}
        }}, indent=2)

@dataclass
class RobotState:
    is_moving: bool = False
    last_action_id: Optional[str] = None

class ROSClaw{robot_class}Client:
    def __init__(self, node_name: str = "rosclaw_{context.robot_name}_mcp"):
        if not rclpy.ok():
            rclpy.init()
        self.node = Node(node_name)
        self.state = RobotState()
        self._active_tasks: Dict[str, Any] = {{}}
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self.node)
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

    # Standard 6: Semantic Spatial Binding
    async def lookup_tf_pose(self, target_frame: str, reference_frame: str = "base_link") -> Optional[Pose]:
        try:
            transform = self._tf_buffer.lookup_transform(reference_frame, target_frame, rclpy.time.Time())
            pose = Pose()
            pose.position.x = transform.transform.translation.x
            pose.position.y = transform.transform.translation.y
            pose.position.z = transform.transform.translation.z
            pose.orientation = transform.transform.rotation
            return pose
        except Exception as e:
            logger.warning(f"TF lookup failed: {{e}}")
            return None

    # Standard 4: Graceful Preemption
    async def cancel_action(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self._active_tasks:
            return {{"success": False, "error": f"No active action: {{task_id}}"}}
        goal_handle = self._active_tasks[task_id]
        cancel_future = goal_handle.cancel_goal_async()
        await self._await_future(cancel_future)
        del self._active_tasks[task_id]
        return {{"success": True, "message": f"Action {{task_id}} canceled"}}

    async def _await_future(self, future: Any, timeout: float = 30.0) -> Any:
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        while not future.done():
            if loop.time() - start_time > timeout:
                raise TimeoutError(f"Future timeout after {{timeout}}s")
            await asyncio.sleep(0.01)
        return future.result()

mcp = FastMCP("rosclaw-{context.robot_name}")
client: Optional[ROSClaw{robot_class}Client] = None

@mcp.on_startup
async def on_startup():
    global client
    client = ROSClaw{robot_class}Client()
    await client.start()
    logger.info("ROSClaw {context.robot_name} MCP Server ready")

@mcp.on_shutdown
async def on_shutdown():
    global client
    if client:
        await client.stop()

@mcp.tool()
async def get_state() -> str:
    if not client:
        return json.dumps({{"error": "Client not initialized"}})
    return json.dumps({{
        "is_moving": client.state.is_moving,
        "last_action_id": client.state.last_action_id
    }})

@mcp.tool()
async def lookup_tf_pose_tool(target_frame: str, reference_frame: str = "base_link") -> str:
    if not client:
        return json.dumps({{"error": "Client not initialized"}})
    pose = await client.lookup_tf_pose(target_frame, reference_frame)
    if pose:
        return json.dumps({{"success": True, "pose": {{
            "x": pose.position.x, "y": pose.position.y, "z": pose.position.z
        }}}})
    return json.dumps({{"success": False, "error": "TF lookup failed"}})

@mcp.tool()
async def cancel_action_tool(task_id: str) -> str:
    if not client:
        return json.dumps({{"error": "Client not initialized"}})
    result = await client.cancel_action(task_id)
    return json.dumps(result)

if __name__ == "__main__":
    mcp.run(transport="stdio")
'''


class TheCriticWrapper:
    """
    第三阶段：审查官 Agent 包装器

    验证生成的代码是否符合 6 大 ROSClaw-Native 标准。
    如果不符合，返回修复建议。
    """

    def __init__(self):
        self.critic = CriticAgent()

    def review(self, context: AgenticContext) -> Tuple[bool, str]:
        """
        审查代码

        Returns:
            (是否通过, 反馈信息)
        """
        print(f"\n[CRITIC] 🔍 Reviewing code against ROSClaw-Native Standards...")

        # 使用 CriticAgent 进行审查
        passed, feedback = the_critic(context.mcp_code)

        # 记录审查报告
        context.critic_report = self.critic.review(context.mcp_code)

        if passed:
            print(f"[CRITIC] ✅ Code meets all 6 ROSClaw-Native standards!")
        else:
            print(f"[CRITIC] ❌ Found violations:")
            for line in feedback.split("\n")[:5]:  # 只显示前5条
                print(f"         {line}")

        return passed, feedback


class AgenticCompiler:
    """
    🎭 Agentic Asset Bundle Compiler

    主编排器，协调三个 Agent 完成代码生成和自我修复。
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_retries: int = 5
    ):
        self.llm_client = llm_client
        self.max_retries = max_retries

        # 初始化三个 Agent
        self.ingestor = TheIngestor(llm_client)
        self.generator = TheGenerator(llm_client)
        self.critic = TheCriticWrapper()

    def compile(
        self,
        robot_name: str,
        vendor: str,
        robot_type: str,
        sdk_docs: str,
        output_dir: str = "generated"
    ) -> AgenticResult:
        """
        主入口：编译具身资产包

        执行完整的 Agentic Workflow：
        Ingestor -> Generator -> Critic (循环直到通过)
        """
        print("\n" + "=" * 60)
        print("🚀 AGENTIC ASSET BUNDLE COMPILER V2.0")
        print("=" * 60)

        # 初始化上下文
        context = AgenticContext(
            robot_name=robot_name,
            vendor=vendor,
            robot_type=robot_type,
            sdk_docs=sdk_docs,
            max_retries=self.max_retries
        )

        attempts = []

        # === Stage 1: Ingestor ===
        context = self.ingestor.ingest(context)

        # === Stage 2 & 3: Generator + Critic Loop ===
        for attempt in range(1, self.max_retries + 1):
            context.attempt_number = attempt
            print(f"\n{'=' * 60}")
            print(f"🔄 COMPILATION ATTEMPT {attempt}/{self.max_retries}")
            print("=" * 60)

            # Generate
            context = self.generator.generate(context)

            # Review
            passed, feedback = self.critic.review(context)

            attempts.append({
                "attempt": attempt,
                "passed": passed,
                "message": feedback[:100] + "..." if len(feedback) > 100 else feedback
            })

            if passed:
                # 成功！打包资产
                print(f"\n[BUNDLER] 📦 Creating embodied asset bundle...")
                output_path = self._create_bundle(context, output_dir)

                return AgenticResult(
                    success=True,
                    context=context,
                    attempts=attempts,
                    output_dir=output_path
                )
            else:
                # 失败，将反馈加入上下文供下次生成使用
                print(f"\n[HEALER] 🔄 Self-healing triggered. Sending feedback to Generator...")
                context.sdk_docs += f"\n\n[PREVIOUS_ATTEMPT_FEEDBACK]\n{feedback}\n\nPlease fix these issues."

        # 超过最大重试次数
        return AgenticResult(
            success=False,
            context=context,
            attempts=attempts
        )

    def _create_bundle(self, context: AgenticContext, output_dir: str) -> str:
        """创建具身资产包"""
        from embodied_asset_bundle import create_embodied_asset_bundle

        return create_embodied_asset_bundle(
            robot_name=context.robot_name,
            mcp_code=context.mcp_code,
            robot_type=context.robot_type,
            vendor=context.vendor,
            ros2_interfaces=context.ros2_interfaces,
            safety_limits=context.safety_constraints.get("limits", {}),
            description=f"ROSClaw-Native MCP Server for {context.vendor} {context.robot_name}"
        )


# 便捷的入口函数
def generate_with_critic(
    robot_name: str,
    vendor: str,
    robot_type: str,
    sdk_docs: str,
    llm_client: Optional[Any] = None,
    max_retries: int = 5,
    output_dir: str = "generated"
) -> AgenticResult:
    """
    快速入口：使用 Agentic Compiler 生成 MCP Server

    Args:
        robot_name: 机器人名称
        vendor: 厂商名称
        robot_type: 机器人类型 (arm/mobile/humanoid/drone)
        sdk_docs: SDK 文档内容
        llm_client: LLM 客户端 (可选)
        max_retries: 最大重试次数
        output_dir: 输出目录

    Returns:
        AgenticResult: 编译结果
    """
    compiler = AgenticCompiler(llm_client=llm_client, max_retries=max_retries)
    return compiler.compile(
        robot_name=robot_name,
        vendor=vendor,
        robot_type=robot_type,
        sdk_docs=sdk_docs,
        output_dir=output_dir
    )


if __name__ == "__main__":
    # 测试用例
    test_docs = """
    # Test Robot SDK

    ## ROS 2 Actions
    - test_msgs::action::MoveRobot
    - test_msgs::action::QueryState

    ## Safety Limits
    Velocity limit: 1.0 m/s
    Position limit: -3.14 to 3.14 rad
    """

    result = generate_with_critic(
        robot_name="test_bot",
        vendor="TestCorp",
        robot_type="arm",
        sdk_docs=test_docs,
        max_retries=3
    )

    print(result.get_summary())
