#!/usr/bin/env python3
"""
🎭 The Critic Agent - ROSClaw Architecture Guardian

SDK-to-MCP V2.0 的核心壁垒。
审查生成的代码是否符合 6 大 ROSClaw-Native 标准。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class CriticSeverity(Enum):
    """审查问题严重程度"""
    CRITICAL = "CRITICAL"  # 必须修复，否则代码无法运行
    HIGH = "HIGH"          # 严重违反标准，必须修复
    MEDIUM = "MEDIUM"      # 建议修复，但非阻塞
    LOW = "LOW"            # 风格问题，可选修复


@dataclass
class CriticIssue:
    """审查发现的问题"""
    severity: CriticSeverity
    standard: str          # 违反的标准编号 (1-6)
    message: str
    line_number: Optional[int] = None
    suggestion: str = ""


@dataclass
class CriticReport:
    """审查报告"""
    passed: bool
    issues: List[CriticIssue] = field(default_factory=list)
    summary: str = ""

    def get_critical_errors(self) -> List[CriticIssue]:
        return [i for i in self.issues if i.severity == CriticSeverity.CRITICAL]

    def get_high_errors(self) -> List[CriticIssue]:
        return [i for i in self.issues if i.severity == CriticSeverity.HIGH]

    def to_string(self) -> str:
        lines = ["=" * 60, "🎭 CRITIC AGENT REPORT", "=" * 60]
        lines.append(f"\nStatus: {'✅ PASSED' if self.passed else '❌ FAILED'}")
        lines.append(f"Total Issues: {len(self.issues)}")

        for severity in [CriticSeverity.CRITICAL, CriticSeverity.HIGH,
                        CriticSeverity.MEDIUM, CriticSeverity.LOW]:
            severity_issues = [i for i in self.issues if i.severity == severity]
            if severity_issues:
                lines.append(f"\n{severity.value} ({len(severity_issues)}):")
                for issue in severity_issues:
                    line_info = f" (Line {issue.line_number})" if issue.line_number else ""
                    lines.append(f"  [标准{issue.standard}] {issue.message}{line_info}")
                    if issue.suggestion:
                        lines.append(f"    💡 {issue.suggestion}")

        lines.append(f"\n{'=' * 60}")
        return "\n".join(lines)


class CriticAgent:
    """
    ROSClaw 架构审查官

    对生成的 MCP Server 代码进行严格的 6 大标准审查。
    """

    # 标准检查点
    STANDARDS = {
        "1": "Absolute Async (异步动作)",
        "2": "Flywheel-Ready JSON (飞轮就绪响应)",
        "3": "Native Firewall Hook (防火墙集成)",
        "4": "Graceful Preemption (优雅抢占)",
        "5": "State-Aware Affordance (状态感知)",
        "6": "Semantic Spatial Binding (语义空间绑定)",
    }

    def __init__(self):
        self.code: str = ""
        self.ast_tree: Optional[ast.AST] = None

    def review(self, code: str) -> CriticReport:
        """
        主审查入口

        Args:
            code: 待审查的 Python 代码

        Returns:
            CriticReport: 审查报告
        """
        self.code = code
        issues: List[CriticIssue] = []

        # 尝试解析 AST
        try:
            self.ast_tree = ast.parse(code)
        except SyntaxError as e:
            return CriticReport(
                passed=False,
                issues=[CriticIssue(
                    severity=CriticSeverity.CRITICAL,
                    standard="0",
                    message=f"Syntax Error: {str(e)}",
                    line_number=e.lineno
                )],
                summary="Code has syntax errors and cannot be reviewed."
            )

        # 执行各项标准检查
        issues.extend(self._check_standard_1_async())
        issues.extend(self._check_standard_2_flywheel_json())
        issues.extend(self._check_standard_3_firewall())
        issues.extend(self._check_standard_4_preemption())
        issues.extend(self._check_standard_5_state_aware())
        issues.extend(self._check_standard_6_tf2_binding())

        # 计算结果
        critical_count = len([i for i in issues if i.severity == CriticSeverity.CRITICAL])
        high_count = len([i for i in issues if i.severity == CriticSeverity.HIGH])

        passed = critical_count == 0 and high_count == 0

        summary = f"Review Complete: {len(issues)} issues found. "
        if passed:
            summary += "All ROSClaw-Native standards satisfied! ✅"
        else:
            summary += f"Please fix {critical_count} critical and {high_count} high severity issues."

        return CriticReport(passed=passed, issues=issues, summary=summary)

    def _check_standard_1_async(self) -> List[CriticIssue]:
        """检查标准 1: Absolute Async"""
        issues = []

        # 检查是否有 async def
        async_funcs = re.findall(r'async\s+def\s+(\w+)', self.code)
        if not async_funcs:
            issues.append(CriticIssue(
                severity=CriticSeverity.CRITICAL,
                standard="1",
                message="No async functions found. All MCP tools must use 'async def'.",
                suggestion="Add 'async' keyword to all tool functions: async def tool_name(...)"
            ))

        # 检查是否有 await (简单检查)
        if 'await ' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="1",
                message="No 'await' statements found. Async functions must await ROS 2 actions.",
                suggestion="Use 'await action_client.send_goal_async(...)' for non-blocking calls."
            ))

        # 检查物理动作函数是否都是 async
        physical_patterns = ['move_', 'execute_', 'navigate_', 'grasp_', 'rotate_']
        for pattern in physical_patterns:
            matches = re.findall(rf'def\s+({pattern}\w+)\s*\(', self.code)
            for match in matches:
                if f'async def {match}' not in self.code:
                    issues.append(CriticIssue(
                        severity=CriticSeverity.HIGH,
                        standard="1",
                        message=f"Physical action function '{match}' is not async.",
                        suggestion=f"Change 'def {match}' to 'async def {match}'"
                    ))

        return issues

    def _check_standard_2_flywheel_json(self) -> List[CriticIssue]:
        """检查标准 2: Flywheel-Ready JSON"""
        issues = []

        # 检查是否有 ActionStatus 或类似的状态枚举
        if 'ActionStatus' not in self.code and 'NavigationStatus' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="2",
                message="Missing ActionStatus enum. Must define status states for Data Flywheel.",
                suggestion="Define: class ActionStatus(Enum): PENDING = 'PENDING'; EXECUTING = 'EXECUTING'; ..."
            ))

        # 检查是否有 to_json 或 to_dict 方法
        if 'to_json' not in self.code and 'to_dict' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="2",
                message="Missing to_json() or to_dict() method. Results must be serializable.",
                suggestion="Add to_json() method to result dataclass returning json.dumps({...})"
            ))

        # 检查必需的 Flywheel 字段
        required_fields = ['status', 'action_id', 'semantic_goal', 'timestamp_start']
        for field in required_fields:
            if field not in self.code:
                issues.append(CriticIssue(
                    severity=CriticSeverity.HIGH,
                    standard="2",
                    message=f"Missing required Flywheel field '{field}' in result structure.",
                    suggestion=f"Add '{field}' field to your result dataclass."
                ))

        return issues

    def _check_standard_3_firewall(self) -> List[CriticIssue]:
        """检查标准 3: Native Firewall Hook"""
        issues = []

        # 检查是否导入了防火墙装饰器
        if 'mujoco_firewall' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="3",
                message="Missing mujoco_firewall import. Physical moves require firewall validation.",
                suggestion="Add: from rosclaw.firewall.decorator import mujoco_firewall, SafetyLevel"
            ))

        # 检查是否有 @mujoco_firewall 装饰器
        if '@mujoco_firewall' not in self.code:
            # 查找物理动作函数
            physical_funcs = re.findall(r'async\s+def\s+(move_\w+|execute_\w+|navigate_\w+)', self.code)
            if physical_funcs:
                issues.append(CriticIssue(
                    severity=CriticSeverity.HIGH,
                    standard="3",
                    message=f"Physical action functions found but none use @mujoco_firewall: {physical_funcs}",
                    suggestion="Add @mujoco_firewall(model_path='...', safety_level=SafetyLevel.STRICT) decorator."
                ))

        # 检查是否有 firewalled 版本和非 firewalled 版本
        firewalled_funcs = re.findall(r'@mujoco_firewall[\s\S]*?async\s+def\s+(\w+)', self.code)
        if firewalled_funcs:
            for func in firewalled_funcs:
                base_name = func.replace('_firewalled', '')
                if base_name == func or f'async def {base_name}' not in self.code:
                    issues.append(CriticIssue(
                        severity=CriticSeverity.MEDIUM,
                        standard="3",
                        message=f"Firewalled function '{func}' should have a non-firewalled counterpart.",
                        suggestion=f"Also implement '{base_name}' without firewall for fast-path operations."
                    ))

        return issues

    def _check_standard_4_preemption(self) -> List[CriticIssue]:
        """检查标准 4: Graceful Preemption"""
        issues = []

        # 检查是否有 cancel_action 函数
        if 'cancel_action' not in self.code and 'cancel_' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="4",
                message="Missing cancel_action function. Must support graceful preemption.",
                suggestion="Implement: async def cancel_action(self, task_id: str) -> Dict[str, Any]"
            ))

        # 检查是否有 _active_tasks 跟踪
        if '_active_tasks' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="4",
                message="Missing active task tracking. Cannot cancel without tracking.",
                suggestion="Add: self._active_tasks: Dict[str, Any] = {} to track goal handles."
            ))

        # 检查是否有 cancel_goal_async 调用
        if 'cancel_goal_async' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.MEDIUM,
                standard="4",
                message="Not using cancel_goal_async(). Preemption may not work correctly.",
                suggestion="Use: cancel_future = goal_handle.cancel_goal_async()"
            ))

        return issues

    def _check_standard_5_state_aware(self) -> List[CriticIssue]:
        """检查标准 5: State-Aware Affordance"""
        issues = []

        # 检查是否有状态类
        if 'RobotState' not in self.code and 'NavigationState' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="5",
                message="Missing state class. Must implement local state machine.",
                suggestion="Add: @dataclass class RobotState: is_moving: bool = False; ..."
            ))

        # 检查是否有 is_moving 或 is_navigating 检查
        state_checks = ['is_moving', 'is_navigating', 'is_executing']
        if not any(check in self.code for check in state_checks):
            issues.append(CriticIssue(
                severity=CriticSeverity.HIGH,
                standard="5",
                message="No state validation before actions. Robot may receive conflicting commands.",
                suggestion="Add: if self.state.is_moving: return REJECTED error before executing."
            ))

        return issues

    def _check_standard_6_tf2_binding(self) -> List[CriticIssue]:
        """检查标准 6: Semantic Spatial Binding"""
        issues = []

        # 检查是否导入 tf2_ros
        if 'tf2_ros' not in self.code and 'tf2' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.MEDIUM,
                standard="6",
                message="Missing TF2 imports. Cannot provide semantic spatial binding.",
                suggestion="Add: import tf2_ros; from tf2_ros import TransformListener"
            ))

        # 检查是否有 lookup_tf_pose 函数
        if 'lookup_tf_pose' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.MEDIUM,
                standard="6",
                message="Missing lookup_tf_pose function. Cannot abstract 3D math from LLM.",
                suggestion="Implement: async def lookup_tf_pose(self, target_frame, reference_frame) -> Pose"
            ))

        # 检查是否有 TF2 Buffer
        if 'Buffer()' not in self.code and 'tf_buffer' not in self.code:
            issues.append(CriticIssue(
                severity=CriticSeverity.LOW,
                standard="6",
                message="TF2 Buffer not initialized.",
                suggestion="Add: self._tf_buffer = tf2_ros.Buffer() in __init__"
            ))

        return issues


def the_critic(code: str) -> Tuple[bool, str]:
    """
    快速入口函数，返回 (是否通过, 错误信息)

    与 self_healing_generator.py 兼容的接口。
    """
    agent = CriticAgent()
    report = agent.review(code)

    if report.passed:
        return True, "✅ Critic Approved: Code meets all ROSClaw-Native standards."
    else:
        # 构建错误信息字符串
        error_lines = []
        for issue in report.get_critical_errors() + report.get_high_errors():
            error_lines.append(f"[标准{issue.standard}] {issue.message}")
            if issue.suggestion:
                error_lines.append(f"  💡 {issue.suggestion}")

        return False, "\n".join(error_lines)


if __name__ == "__main__":
    # 测试用例
    test_code_good = '''
import asyncio
from dataclasses import dataclass
from enum import Enum

class ActionStatus(Enum):
    SUCCEEDED = "SUCCEEDED"

@dataclass
class Result:
    status: ActionStatus
    def to_json(self): return "{}"

class Client:
    def __init__(self):
        self._active_tasks = {}
        self.state = type('State', (), {'is_moving': False})()

    async def cancel_action(self, task_id: str):
        return {"success": True}
'''

    agent = CriticAgent()
    report = agent.review(test_code_good)
    print(report.to_string())
