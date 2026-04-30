#!/usr/bin/env python3
"""
🔗 ClawHub Sync Publisher - Ecosystem Registration Bridge

After successful MCP Server generation, this module updates the registry manifest
that powers the rosclaw.io Next.js website.

Connects the Agentic Compiler to the ClawHub ecosystem!
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class MCPToolDefinition:
    """MCP Tool metadata for registry"""
    name: str
    description: str
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    returns: Dict[str, Any] = field(default_factory=dict)
    is_async: bool = True
    has_firewall: bool = False
    is_preemptible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "returns": self.returns,
            "is_async": self.is_async,
            "has_firewall": self.has_firewall,
            "is_preemptible": self.is_preemptible,
        }


@dataclass
class SafetyConstraint:
    """Safety constraint metadata"""
    type: str  # "velocity", "position", "force", "temperature"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "min": self.min_value,
            "max": self.max_value,
            "unit": self.unit,
            "description": self.description,
        }


@dataclass
class FirewallConfig:
    """Digital Twin Firewall configuration"""
    enabled: bool = True
    safety_level: str = "STRICT"  # STRICT, MODERATE, LENIENT
    mujoco_model: str = ""
    collision_pairs: List[List[str]] = field(default_factory=list)
    validation_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "safety_level": self.safety_level,
            "mujoco_model": self.mujoco_model,
            "collision_pairs": self.collision_pairs,
            "validation_rules": self.validation_rules,
        }


@dataclass
class RobotRegistryEntry:
    """Complete robot registry entry"""
    # Identity
    name: str
    display_name: str
    vendor: str
    type: str  # arm, mobile, humanoid, drone
    ros_version: str = "humble"

    # Metadata
    description: str = ""
    version: str = "1.0.0"
    author: str = "ROSClaw Team"
    license: str = "Apache-2.0"

    # Links
    github_url: str = ""
    documentation_url: str = ""
    pypi_package: str = ""

    # Technical
    mcp_tools: List[MCPToolDefinition] = field(default_factory=list)
    ros2_interfaces: List[str] = field(default_factory=list)
    safety_constraints: List[SafetyConstraint] = field(default_factory=list)
    firewall: FirewallConfig = field(default_factory=FirewallConfig)

    # Capabilities
    supports_async: bool = True
    supports_preemption: bool = True
    supports_tf2: bool = True
    supports_firewall: bool = True

    # Status
    status: str = "beta"  # alpha, beta, stable
    added_date: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": {
                "name": self.name,
                "display_name": self.display_name,
                "vendor": self.vendor,
                "type": self.type,
                "ros_version": self.ros_version,
            },
            "metadata": {
                "description": self.description,
                "version": self.version,
                "author": self.author,
                "license": self.license,
            },
            "links": {
                "github": self.github_url,
                "docs": self.documentation_url,
                "pypi": self.pypi_package,
            },
            "technical": {
                "mcp_tools": [t.to_dict() for t in self.mcp_tools],
                "ros2_interfaces": self.ros2_interfaces,
                "safety_constraints": [s.to_dict() for s in self.safety_constraints],
                "firewall": self.firewall.to_dict(),
            },
            "capabilities": {
                "async": self.supports_async,
                "preemption": self.supports_preemption,
                "tf2": self.supports_tf2,
                "firewall": self.supports_firewall,
            },
            "status": {
                "state": self.status,
                "added": self.added_date,
                "updated": self.last_updated,
            },
        }


class HubSyncPublisher:
    """
    ClawHub Registry Sync Publisher

    Manages the registry manifest that powers rosclaw.io
    """

    def __init__(self, registry_path: Optional[str] = None):
        self.registry_path = Path(registry_path or "registry_manifest.json")
        self.manifest: Dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Any]:
        """Load existing manifest or create new"""
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Create new manifest structure
        return {
            "schema_version": "2.0",
            "last_updated": datetime.now().isoformat(),
            "total_robots": 0,
            "categories": {
                "arm": {"count": 0, "robots": []},
                "mobile": {"count": 0, "robots": []},
                "humanoid": {"count": 0, "robots": []},
                "drone": {"count": 0, "robots": []},
            },
            "robots": {},
            "statistics": {
                "total_mcp_tools": 0,
                "total_safety_constraints": 0,
                "firewall_coverage": 0.0,
            },
        }

    def add_robot(self, entry: RobotRegistryEntry) -> None:
        """Add or update a robot in the registry"""
        robot_id = f"{entry.vendor.lower()}_{entry.name.lower()}"

        # Update main robots dict
        self.manifest["robots"][robot_id] = entry.to_dict()

        # Update category
        category = entry.type
        if category in self.manifest["categories"]:
            if robot_id not in self.manifest["categories"][category]["robots"]:
                self.manifest["categories"][category]["robots"].append(robot_id)
                self.manifest["categories"][category]["count"] += 1

        # Update totals
        self.manifest["total_robots"] = len(self.manifest["robots"])
        self.manifest["last_updated"] = datetime.now().isoformat()

        # Recalculate statistics
        self._update_statistics()

        print(f"[HUB_SYNC] ✅ Added {entry.display_name} to registry")
        print(f"[HUB_SYNC]    Tools: {len(entry.mcp_tools)}")
        print(f"[HUB_SYNC]    Safety Constraints: {len(entry.safety_constraints)}")

    def _update_statistics(self) -> None:
        """Update aggregate statistics"""
        total_tools = 0
        total_safety = 0
        firewall_count = 0

        for robot in self.manifest["robots"].values():
            tech = robot.get("technical", {})
            total_tools += len(tech.get("mcp_tools", []))
            total_safety += len(tech.get("safety_constraints", []))
            if tech.get("firewall", {}).get("enabled", False):
                firewall_count += 1

        self.manifest["statistics"]["total_mcp_tools"] = total_tools
        self.manifest["statistics"]["total_safety_constraints"] = total_safety

        if self.manifest["total_robots"] > 0:
            self.manifest["statistics"]["firewall_coverage"] = (
                firewall_count / self.manifest["total_robots"] * 100
            )

    def save(self) -> None:
        """Save manifest to disk"""
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)
        print(f"[HUB_SYNC] 💾 Registry saved to {self.registry_path}")

    def generate_nextjs_data(self, output_dir: str = "clawhub_data") -> None:
        """
        Generate TypeScript data files for Next.js frontend
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Generate robots.ts
        robots_ts = self._generate_robots_ts()
        (output_path / "robots.ts").write_text(robots_ts, encoding="utf-8")

        # Generate stats.ts
        stats_ts = self._generate_stats_ts()
        (output_path / "stats.ts").write_text(stats_ts, encoding="utf-8")

        print(f"[HUB_SYNC] 🚀 Next.js data exported to {output_dir}/")

    def _generate_robots_ts(self) -> str:
        """Generate TypeScript robots data file"""
        lines = [
            "// Auto-generated by HubSyncPublisher",
            "// DO NOT EDIT MANUALLY",
            "",
            "export interface Robot {",
            "  id: string;",
            "  name: string;",
            "  vendor: string;",
            "  type: 'arm' | 'mobile' | 'humanoid' | 'drone';",
            "  description: string;",
            "  githubUrl: string;",
            "  docsUrl: string;",
            "  tools: string[];",
            "  safetyLevel: string;",
            "  status: string;",
            "}",
            "",
            "export const robots: Robot[] = [",
        ]

        for robot_id, robot in self.manifest["robots"].items():
            identity = robot.get("identity", {})
            links = robot.get("links", {})
            technical = robot.get("technical", {})

            tools = [t["name"] for t in technical.get("mcp_tools", [])]
            safety_level = technical.get("firewall", {}).get("safety_level", "NONE")

            lines.append("  {")
            lines.append(f'    id: "{robot_id}",')
            lines.append(f'    name: "{identity.get("display_name", "")}",')
            lines.append(f'    vendor: "{identity.get("vendor", "")}",')
            lines.append(f'    type: "{identity.get("type", "arm")}",')
            lines.append(f'    description: "{identity.get("description", "")[:100]}...",')
            lines.append(f'    githubUrl: "{links.get("github", "")}",')
            lines.append(f'    docsUrl: "{links.get("docs", "")}",')
            lines.append(f'    tools: {json.dumps(tools)},')
            lines.append(f'    safetyLevel: "{safety_level}",')
            lines.append(f'    status: "{robot.get("status", {}).get("state", "beta")}",')
            lines.append("  },")

        lines.append("];")
        return "\n".join(lines)

    def _generate_stats_ts(self) -> str:
        """Generate TypeScript stats data file"""
        stats = self.manifest.get("statistics", {})

        return f"""// Auto-generated by HubSyncPublisher
// DO NOT EDIT MANUALLY

export const clawHubStats = {{
  totalRobots: {self.manifest.get("total_robots", 0)},
  totalTools: {stats.get("total_mcp_tools", 0)},
  totalSafetyConstraints: {stats.get("total_safety_constraints", 0)},
  firewallCoverage: {stats.get("firewall_coverage", 0):.1f},
  lastUpdated: "{self.manifest.get("last_updated", "")}",
  categories: {{
    arm: {self.manifest.get("categories", {}).get("arm", {}).get("count", 0)},
    mobile: {self.manifest.get("categories", {}).get("mobile", {}).get("count", 0)},
    humanoid: {self.manifest.get("categories", {}).get("humanoid", {}).get("count", 0)},
    drone: {self.manifest.get("categories", {}).get("drone", {}).get("count", 0)},
  }},
}};
"""


def update_registry_manifest(
    robot_name: str,
    vendor: str,
    robot_type: str,
    mcp_tools: List[Dict[str, Any]],
    safety_constraints: List[Dict[str, Any]],
    github_url: str = "",
    registry_path: Optional[str] = None,
) -> str:
    """
    Quick entry point to update registry after successful generation.

    Returns the path to the updated registry file.
    """
    publisher = HubSyncPublisher(registry_path)

    # Create entry
    entry = RobotRegistryEntry(
        name=robot_name,
        display_name=f"{vendor} {robot_name.replace('_', ' ').title()}",
        vendor=vendor,
        type=robot_type,
        github_url=github_url,
        pypi_package=f"rosclaw-{robot_name}-mcp",
    )

    # Add tools
    for tool_data in mcp_tools:
        entry.mcp_tools.append(MCPToolDefinition(
            name=tool_data.get("name", ""),
            description=tool_data.get("description", ""),
            is_async=tool_data.get("is_async", True),
            has_firewall=tool_data.get("has_firewall", False),
            is_preemptible=tool_data.get("is_preemptible", False),
        ))

    # Add safety constraints
    for constraint_data in safety_constraints:
        entry.safety_constraints.append(SafetyConstraint(
            type=constraint_data.get("type", ""),
            min_value=constraint_data.get("min"),
            max_value=constraint_data.get("max"),
            unit=constraint_data.get("unit", ""),
            description=constraint_data.get("description", ""),
        ))

    # Enable firewall if there are safety constraints
    if safety_constraints:
        entry.firewall.enabled = True
        entry.firewall.safety_level = "STRICT"
        entry.firewall.validation_rules = [
            "Check joint limits before execution",
            "Validate velocity constraints",
            "Ensure collision-free trajectory",
        ]

    # Add to registry
    publisher.add_robot(entry)
    publisher.save()

    return str(publisher.registry_path)


# Test
if __name__ == "__main__":
    publisher = HubSyncPublisher()

    # Add test robot
    entry = RobotRegistryEntry(
        name="unitree_go2",
        display_name="Unitree Go2 Quadruped",
        vendor="Unitree",
        type="mobile",
        description="ROSClaw-Native MCP Server for Unitree Go2 quadruped robot",
        github_url="https://github.com/ros-claw/rosclaw_unitree_go2_mcp",
    )

    entry.mcp_tools = [
        MCPToolDefinition(
            name="walk",
            description="Walk to target position",
            has_firewall=True,
            is_preemptible=True,
        ),
        MCPToolDefinition(
            name="stand_up",
            description="Stand up from lying position",
            has_firewall=True,
        ),
    ]

    entry.safety_constraints = [
        SafetyConstraint(
            type="velocity",
            min_value=0.0,
            max_value=1.5,
            unit="m/s",
            description="Maximum walking speed",
        ),
    ]

    publisher.add_robot(entry)
    publisher.save()
    publisher.generate_nextjs_data()
