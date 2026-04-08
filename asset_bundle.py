"""
Asset Bundle Generator Module

Generates standardized Embodied Asset Bundle output format:
    output/
    ├── server.py              # Auto-generated FastMCP server
    ├── e_urdf.json            # Auto-generated semantic & safety config
    ├── requirements.txt       # Auto-analyzed dependencies
    └── prompts/
        ├── system.md          # LLM system prompt for this robot
        └── tools_usage.md     # LLM tools usage guide

Key concept: The output is not just a Python file, but a complete package
that can be published to e-URDF-Zoo and used by any MCP-compatible agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class AssetBundle:
    """
    Complete embodied asset bundle for an MCP server.

    This is the standardized output format for sdk_to_mcp transformation.
    """

    # Robot identification
    robot_id: str
    robot_name: str
    version: str = "1.0.0"

    # Generated files
    server_code: str = ""
    e_urdf_config: dict[str, Any] = field(default_factory=dict)
    requirements: list[str] = field(default_factory=list)

    # LLM prompts
    system_prompt: str = ""
    tools_usage_prompt: str = ""

    # Metadata
    description: str = ""
    author: str = "sdk_to_mcp"
    generated_date: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())

    def to_output_dir(self, output_path: Path) -> dict[str, Path]:
        """
        Write all bundle files to output directory.

        Args:
            output_path: Directory to write files to

        Returns:
            Dictionary mapping file names to paths
        """
        output_path.mkdir(parents=True, exist_ok=True)
        files = {}

        # server.py
        if self.server_code:
            server_path = output_path / "server.py"
            server_path.write_text(self.server_code)
            files["server.py"] = server_path

        # e_urdf.json
        if self.e_urdf_config:
            config_path = output_path / "e_urdf.json"
            config_path.write_text(json.dumps(self.e_urdf_config, indent=2))
            files["e_urdf.json"] = config_path

        # requirements.txt
        if self.requirements:
            req_path = output_path / "requirements.txt"
            req_path.write_text("\n".join(self.requirements))
            files["requirements.txt"] = req_path

        # prompts directory
        if self.system_prompt or self.tools_usage_prompt:
            prompts_dir = output_path / "prompts"
            prompts_dir.mkdir(exist_ok=True)

            if self.system_prompt:
                system_path = prompts_dir / "system.md"
                system_path.write_text(self.system_prompt)
                files["prompts/system.md"] = system_path

            if self.tools_usage_prompt:
                usage_path = prompts_dir / "tools_usage.md"
                usage_path.write_text(self.tools_usage_prompt)
                files["prompts/tools_usage.md"] = usage_path

        # manifest.json
        manifest = {
            "robot_id": self.robot_id,
            "robot_name": self.robot_name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "generated_date": self.generated_date,
            "files": list(files.keys()),
        }
        manifest_path = output_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        files["manifest.json"] = manifest_path

        return files

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate the asset bundle is complete.

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        if not self.robot_id:
            errors.append("Missing robot_id")

        if not self.server_code:
            errors.append("Missing server_code")
        elif "FastMCP" not in self.server_code:
            errors.append("Server code missing FastMCP initialization")
        elif "@mcp.tool()" not in self.server_code:
            errors.append("Server code missing @mcp.tool() decorators")

        if not self.e_urdf_config:
            errors.append("Missing e_urdf_config")
        else:
            required_keys = ["embodiment_id", "kinematics", "joints"]
            for key in required_keys:
                if key not in self.e_urdf_config:
                    errors.append(f"e_urdf_config missing required key: {key}")

        if not self.requirements:
            errors.append("Missing requirements")
        elif "mcp" not in " ".join(self.requirements).lower():
            errors.append("Requirements missing mcp dependency")

        return len(errors) == 0, errors


class AssetBundleGenerator:
    """
    Generates complete AssetBundle from SDK transformation results.
    """

    def __init__(self):
        self.dependencies_analyzer = DependenciesAnalyzer()

    def generate(
        self,
        robot_id: str,
        robot_name: str,
        server_code: str,
        hardware_specs: dict[str, Any],
        protocol_info: dict[str, Any],
        safety_constraints: list[dict],
    ) -> AssetBundle:
        """
        Generate complete asset bundle.

        Args:
            robot_id: Unique robot identifier
            robot_name: Human-readable robot name
            server_code: Generated MCP server Python code
            hardware_specs: Hardware specifications
            protocol_info: Protocol information
            safety_constraints: List of safety constraints

        Returns:
            Complete AssetBundle
        """
        # Analyze dependencies from code
        requirements = self.dependencies_analyzer.analyze(server_code)

        # Generate e-URDF config
        e_urdf_config = self._generate_e_urdf_config(
            robot_id=robot_id,
            robot_name=robot_name,
            hardware_specs=hardware_specs,
            safety_constraints=safety_constraints,
        )

        # Generate prompts
        system_prompt = self._generate_system_prompt(
            robot_name=robot_name,
            hardware_specs=hardware_specs,
            protocol_info=protocol_info,
        )

        tools_usage_prompt = self._generate_tools_usage_prompt(
            robot_name=robot_name,
            protocol_info=protocol_info,
        )

        return AssetBundle(
            robot_id=robot_id,
            robot_name=robot_name,
            server_code=server_code,
            e_urdf_config=e_urdf_config,
            requirements=requirements,
            system_prompt=system_prompt,
            tools_usage_prompt=tools_usage_prompt,
            description=hardware_specs.get("description", f"MCP server for {robot_name}"),
        )

    def _generate_e_urdf_config(
        self,
        robot_id: str,
        robot_name: str,
        hardware_specs: dict[str, Any],
        safety_constraints: list[dict],
    ) -> dict[str, Any]:
        """Generate e_urdf.json configuration."""
        config = {
            "embodiment_id": f"{robot_id}_v1",
            "embodiment_name": robot_name,
            "version": "1.0.0",
            "meta": {
                "manufacturer": hardware_specs.get("manufacturer", "Unknown"),
                "model": hardware_specs.get("model", robot_id),
                "description": hardware_specs.get("description", ""),
                "tags": hardware_specs.get("tags", []),
            },
            "kinematics": {
                "base_frame": "base_link",
                "dof": hardware_specs.get("dof", 6),
                "floating_base": hardware_specs.get("floating_base", False),
            },
            "joints": {
                "names": hardware_specs.get("joint_names", []),
                "limits": {
                    "position_rad": {},
                },
            },
            "semantics": {
                "robot_type": hardware_specs.get("robot_type", "arm"),
                "affordances": hardware_specs.get("affordances", []),
            },
            "physical_firewall": {
                "engine": "mujoco",
                "validation_level": "dynamic_stability",
                "mjlab_validation_required": True,
                "max_simulation_horizon_sec": 2.0,
                "speed_up_factor": 100,
                "constraints": {
                    "self_collision": True,
                    "environment_collision": True,
                    "joint_position_limits": True,
                    "joint_velocity_limits": True,
                    "joint_torque_limits": True,
                },
                "safety_margins": {
                    "joint_position": 0.05,
                    "joint_velocity": 0.1,
                    "joint_torque": 0.1,
                },
            },
            "mcp_server_config": {
                "tools": ["verify_action_safety", "get_model_info", "get_joint_limits"],
                "resources": [f"e_urdf://{robot_id}/kinematics"],
            },
        }

        # Add joint limits from safety constraints
        for constraint in safety_constraints:
            param = constraint.get("parameter", "")
            if param in config["joints"]["names"]:
                config["joints"]["limits"]["position_rad"][param] = [
                    constraint.get("min_value", -3.14),
                    constraint.get("max_value", 3.14),
                ]

        return config

    def _generate_system_prompt(
        self,
        robot_name: str,
        hardware_specs: dict[str, Any],
        protocol_info: dict[str, Any],
    ) -> str:
        """Generate LLM system prompt for this robot."""
        return f"""# System Prompt: {robot_name} MCP Server

You are controlling a **{robot_name}** robot through the Model Context Protocol (MCP).

## Robot Specifications

- **Type**: {hardware_specs.get("robot_type", "robotic arm")}
- **Degrees of Freedom**: {hardware_specs.get("dof", 6)}
- **Manufacturer**: {hardware_specs.get("manufacturer", "Unknown")}

## Safety First

⚠️ **CRITICAL**: Before executing ANY physical movement, you MUST use the `verify_action_safety` tool.

1. Plan your trajectory
2. Call `verify_action_safety` with current and target positions
3. Only proceed if the result is SAFE

## Available Capabilities

{chr(10).join(f"- {affordance}" for affordance in hardware_specs.get("affordances", ["manipulation"]))}

## Communication Protocol

This robot uses: **{protocol_info.get("protocol_type", "unknown")}**

## Key Reminders

- Always validate trajectories before execution
- Respect joint limits and safety margins
- Handle errors gracefully
- Ask for clarification if commands are ambiguous

Remember: You are the brain, the MCP server is the nervous system, and the robot is the body.
"""

    def _generate_tools_usage_prompt(
        self,
        robot_name: str,
        protocol_info: dict[str, Any],
    ) -> str:
        """Generate LLM tools usage guide."""
        return f"""# Tools Usage Guide: {robot_name}

## Essential Tools

### 1. verify_action_safety (CRITICAL)

**ALWAYS use this before moving the robot!**

```python
verify_action_safety(
    current_joints=[0, 0, 0, 0, 0, 0],
    target_joints=[0, -1.57, 1.57, 0, 0, 0],
    duration_sec=2.0
)
```

**When to use**: Before ANY physical movement command.

**Response handling**:
- ✅ SAFE: Proceed with execution
- ❌ DANGER: Replan trajectory, DO NOT EXECUTE

### 2. get_model_info

Get robot specifications and joint limits.

```python
get_model_info()
```

**When to use**: At start of session or when you need robot specs.

### 3. get_joint_limits

Get specific joint position/velocity/torque limits.

```python
get_joint_limits()
```

## Best Practices

1. **Plan before acting**: Know your target configuration
2. **Validate first**: Always run safety check
3. **Interpret errors**: Semantic errors tell you what collided
4. **Iterate**: If unsafe, adjust and re-validate

## Example Workflow

```
User: "Move the arm to home position"

You:
1. get_model_info() → Learn joint names
2. verify_action_safety(current, home_target) → Check safety
3. If SAFE: Execute move command
4. If UNSAFE: Explain why and suggest alternative
```
"""


class DependenciesAnalyzer:
    """Analyzes generated code to determine required dependencies."""

    # Common MCP-related dependencies
    DEPENDENCY_MAP = {
        "mcp": "mcp>=1.0.0",
        "fastmcp": "mcp>=1.0.0",
        "numpy": "numpy>=1.20.0",
        "yaml": "pyyaml>=5.4.0",
        "pymodbus": "pymodbus>=2.5.0",
        "serial": "pyserial>=3.5",
        "requests": "requests>=2.25.0",
        "websockets": "websockets>=10.0",
        "socket": None,  # Built-in
        "asyncio": None,  # Built-in
        "json": None,  # Built-in
        "re": None,  # Built-in
        "pathlib": None,  # Built-in
        "typing": None,  # Built-in
        "dataclasses": None,  # Built-in
        "enum": None,  # Built-in
        "datetime": None,  # Built-in
        "rclpy": "rclpy>=3.0.0",
        "std_msgs": None,  # Part of ROS 2
        "geometry_msgs": None,  # Part of ROS 2
        "sensor_msgs": None,  # Part of ROS 2
    }

    def analyze(self, code: str) -> list[str]:
        """
        Analyze code and return list of required dependencies.

        Args:
            code: Python code to analyze

        Returns:
            List of pip requirements
        """
        requirements = set()

        # Parse imports
        try:
            import ast
            tree = ast.parse(code)
        except SyntaxError:
            # Fallback to regex if parsing fails
            return self._analyze_with_regex(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dep = self._get_dependency(alias.name)
                    if dep:
                        requirements.add(dep)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    dep = self._get_dependency(node.module)
                    if dep:
                        requirements.add(dep)

        # Always include mcp
        requirements.add("mcp>=1.0.0")

        return sorted(list(requirements))

    def _analyze_with_regex(self, code: str) -> list[str]:
        """Fallback analysis using regex."""
        requirements = set()

        # Pattern for imports
        import_pattern = r"^(?:import|from)\s+(\w+)"

        import re
        for match in re.finditer(import_pattern, code, re.MULTILINE):
            module = match.group(1)
            dep = self._get_dependency(module)
            if dep:
                requirements.add(dep)

        requirements.add("mcp>=1.0.0")
        return sorted(list(requirements))

    def _get_dependency(self, module: str) -> str | None:
        """Get pip package name for a module."""
        # Direct match
        if module in self.DEPENDENCY_MAP:
            return self.DEPENDENCY_MAP[module]

        # Check if it's a sub-module (e.g., numpy.core)
        base_module = module.split(".")[0]
        if base_module in self.DEPENDENCY_MAP:
            return self.DEPENDENCY_MAP[base_module]

        # Unknown module, skip
        return None


# Example usage
if __name__ == "__main__":
    generator = AssetBundleGenerator()

    bundle = generator.generate(
        robot_id="test_robot",
        robot_name="Test Robot Arm",
        server_code='''
from mcp.server.fastmcp import FastMCP
import numpy as np

mcp = FastMCP("test-robot")

@mcp.tool()
def move_robot(x: float, y: float, z: float) -> str:
    """Move robot to position."""
    return f"Moving to ({x}, {y}, {z})"

def main():
    mcp.run()

if __name__ == "__main__":
    main()
''',
        hardware_specs={
            "manufacturer": "TestCorp",
            "model": "TR-100",
            "dof": 6,
            "robot_type": "arm",
            "affordances": ["manipulation", "grasping"],
            "joint_names": ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"],
        },
        protocol_info={"protocol_type": "TCP"},
        safety_constraints=[],
    )

    # Validate
    is_valid, errors = bundle.validate()
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Errors: {errors}")

    # Write to output
    import tempfile
    output_dir = Path(tempfile.mkdtemp())
    files = bundle.to_output_dir(output_dir)
    print(f"\nGenerated files:")
    for name, path in files.items():
        print(f"  {name}: {path}")
