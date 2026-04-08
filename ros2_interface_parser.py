"""
ROS 2 Interface Parser Module

Extracts precise type information from ROS 2 message definitions, service definitions,
and source code. Replaces PDF-based extraction with AST-based code analysis.

Key concept: Robot capabilities are in the code, not just the documentation.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ROS2MessageField:
    """A field in a ROS 2 message."""

    name: str
    type_str: str
    is_array: bool
    array_size: int | None = None  # None for dynamic arrays
    default_value: Any = None
    description: str = ""

    def to_python_type(self) -> str:
        """Convert ROS 2 type to Python type annotation."""
        type_mapping = {
            "bool": "bool",
            "int8": "int",
            "uint8": "int",
            "int16": "int",
            "uint16": "int",
            "int32": "int",
            "uint32": "int",
            "int64": "int",
            "uint64": "int",
            "float32": "float",
            "float64": "float",
            "string": "str",
            "time": "Time",
            "duration": "Duration",
            "header": "Header",
        }

        base_type = type_mapping.get(self.type_str, self.type_str)

        if self.is_array:
            if self.array_size is not None:
                return f"list[{base_type}]  # Fixed size: {self.array_size}"
            return f"list[{base_type}]"

        return base_type


@dataclass
class ROS2MessageDefinition:
    """Complete ROS 2 message definition."""

    package: str
    name: str
    fields: list[ROS2MessageField] = field(default_factory=list)
    description: str = ""
    constants: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "package": self.package,
            "name": self.name,
            "full_name": f"{self.package}/{self.name}",
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_str,
                    "python_type": f.to_python_type(),
                    "is_array": f.is_array,
                    "array_size": f.array_size,
                    "default": f.default_value,
                    "description": f.description,
                }
                for f in self.fields
            ],
            "description": self.description,
            "constants": self.constants,
        }


@dataclass
class ROS2ServiceDefinition:
    """ROS 2 Service definition (request + response)."""

    package: str
    name: str
    request: ROS2MessageDefinition | None = None
    response: ROS2MessageDefinition | None = None
    description: str = ""


@dataclass
class ROS2TopicInfo:
    """Information about a ROS 2 topic."""

    name: str
    message_type: str
    is_published: bool
    is_subscribed: bool
    description: str = ""
    qos_profile: str = "default"


class ROS2InterfaceParser:
    """
    Parser for ROS 2 interfaces (messages, services, topics).

    Extracts precise type information from:
    - .msg and .srv files
    - Python source code with ROS 2 publishers/subscribers
    - C++ header files
    - Runtime using `ros2 interface show` command
    """

    # ROS 2 primitive types
    PRIMITIVE_TYPES = {
        "bool",
        "int8",
        "uint8",
        "int16",
        "uint16",
        "int32",
        "uint32",
        "int64",
        "uint64",
        "float32",
        "float64",
        "string",
        "time",
        "duration",
    }

    def __init__(self, ros2_available: bool = True):
        """
        Initialize the parser.

        Args:
            ros2_available: Whether ROS 2 CLI tools are available
        """
        self.ros2_available = ros2_available
        self._msg_cache: dict[str, ROS2MessageDefinition] = {}

    def parse_msg_file(self, msg_path: Path) -> ROS2MessageDefinition:
        """
        Parse a .msg file to extract field definitions.

        Args:
            msg_path: Path to .msg file

        Returns:
            ROS2MessageDefinition with parsed fields
        """
        content = msg_path.read_text()

        # Extract package name from path
        package = self._extract_package_from_path(msg_path)
        name = msg_path.stem

        msg_def = ROS2MessageDefinition(package=package, name=name)

        # Parse each line
        for line in content.split("\n"):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                # Check for field description
                if line.startswith("#") and msg_def.fields:
                    msg_def.fields[-1].description = line[1:].strip()
                continue

            # Parse field definition
            field = self._parse_field_line(line)
            if field:
                msg_def.fields.append(field)

        return msg_def

    def _parse_field_line(self, line: str) -> ROS2MessageField | None:
        """Parse a single field definition line."""
        # Pattern: type field_name default_value
        # Examples:
        #   float64 x
        #   float64 y 0.0
        #   string[] names
        #   int32[10] fixed_array

        # Remove inline comments
        if "#" in line:
            line = line.split("#")[0].strip()

        parts = line.split()
        if len(parts) < 2:
            return None

        type_str = parts[0]
        name = parts[1]
        default_value = parts[2] if len(parts) > 2 else None

        # Check for array type
        is_array = "[" in type_str
        array_size = None

        if is_array:
            # Extract array size if fixed
            match = re.match(r"(.+)\[(\d*)\]", type_str)
            if match:
                type_str = match.group(1)
                size_str = match.group(2)
                if size_str:
                    array_size = int(size_str)

        return ROS2MessageField(
            name=name,
            type_str=type_str,
            is_array=is_array,
            array_size=array_size,
            default_value=default_value,
        )

    def _extract_package_from_path(self, msg_path: Path) -> str:
        """Extract ROS package name from message file path."""
        # Typical path: .../package_name/msg/Message.msg
        parts = msg_path.parts
        for i, part in enumerate(parts):
            if part == "msg" and i > 0:
                return parts[i - 1]
        return "unknown"

    def parse_python_node(self, py_path: Path) -> dict[str, Any]:
        """
        Parse a Python ROS 2 node to extract topic and service information.

        Args:
            py_path: Path to Python file

        Returns:
            Dictionary with topics, services, and message types
        """
        content = py_path.read_text()

        topics = []
        services = []
        message_types = set()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return {"topics": topics, "services": services, "message_types": list(message_types)}

        for node in ast.walk(tree):
            # Look for create_publisher() calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Check for create_publisher, create_subscription, create_service
                    if node.func.attr == "create_publisher":
                        topic_info = self._extract_topic_info(node, is_publisher=True)
                        if topic_info:
                            topics.append(topic_info)
                            message_types.add(topic_info.message_type)

                    elif node.func.attr == "create_subscription":
                        topic_info = self._extract_topic_info(node, is_publisher=False)
                        if topic_info:
                            topics.append(topic_info)
                            message_types.add(topic_info.message_type)

                    elif node.func.attr == "create_service":
                        service_info = self._extract_service_info(node)
                        if service_info:
                            services.append(service_info)
                            message_types.add(service_info.get("type", ""))

        return {
            "topics": [t.__dict__ if isinstance(t, ROS2TopicInfo) else t for t in topics],
            "services": services,
            "message_types": sorted(list(message_types)),
        }

    def _extract_topic_info(
        self, node: ast.Call, is_publisher: bool
    ) -> ROS2TopicInfo | None:
        """Extract topic information from a create_publisher/subscription call."""
        if len(node.args) < 2:
            return None

        # Extract message type (first arg)
        msg_type = self._extract_type_from_node(node.args[0])

        # Extract topic name (second arg)
        topic_name = self._extract_string_from_node(node.args[1])

        if msg_type and topic_name:
            return ROS2TopicInfo(
                name=topic_name,
                message_type=msg_type,
                is_published=is_publisher,
                is_subscribed=not is_publisher,
            )

        return None

    def _extract_service_info(self, node: ast.Call) -> dict[str, Any] | None:
        """Extract service information from a create_service call."""
        if len(node.args) < 2:
            return None

        srv_type = self._extract_type_from_node(node.args[0])
        srv_name = self._extract_string_from_node(node.args[1])

        if srv_type and srv_name:
            return {"name": srv_name, "type": srv_type}

        return None

    def _extract_type_from_node(self, node: ast.AST) -> str:
        """Extract type string from AST node."""
        if isinstance(node, ast.Attribute):
            # e.g., std_msgs.msg.String
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        elif isinstance(node, ast.Name):
            return node.id
        return ""

    def _extract_string_from_node(self, node: ast.AST) -> str:
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif isinstance(node, ast.Str):  # Python < 3.8
            return node.s
        return ""

    def ros2_interface_show(self, msg_type: str) -> ROS2MessageDefinition | None:
        """
        Use `ros2 interface show` to get message definition.

        This provides the most accurate type information but requires
        ROS 2 to be installed and sourced.

        Args:
            msg_type: Full message type (e.g., "geometry_msgs/Pose")

        Returns:
            ROS2MessageDefinition or None if not available
        """
        if not self.ros2_available:
            return None

        # Check cache
        if msg_type in self._msg_cache:
            return self._msg_cache[msg_type]

        try:
            result = subprocess.run(
                ["ros2", "interface", "show", msg_type],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return None

            # Parse the output
            parts = msg_type.split("/")
            package = parts[0]
            name = parts[1] if len(parts) > 1 else "Unknown"

            msg_def = ROS2MessageDefinition(package=package, name=name)

            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                field = self._parse_field_line(line)
                if field:
                    msg_def.fields.append(field)

            self._msg_cache[msg_type] = msg_def
            return msg_def

        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.ros2_available = False
            return None

    def parse_cpp_header(self, header_path: Path) -> dict[str, Any]:
        """
        Parse C++ header file for ROS 2 message types.

        Args:
            header_path: Path to .h or .hpp file

        Returns:
            Dictionary with extracted type information
        """
        content = header_path.read_text()

        # Pattern for message type includes
        # #include <geometry_msgs/msg/pose.hpp>
        include_pattern = r'#include\s*[<"](\w+)/msg/(\w+)\.hpp[>"]'

        messages = []
        for match in re.finditer(include_pattern, content):
            package = match.group(1)
            msg_name = match.group(2)
            messages.append(f"{package}/{msg_name}")

        # Pattern for subscriber/publisher declarations
        # rclcpp::Subscription<geometry_msgs::msg::Pose>::SharedPtr sub_;
        sub_pattern = r"(?:Subscription|Publisher)<(\w+)::msg::(\w+)>"

        interfaces = []
        for match in re.finditer(sub_pattern, content):
            package = match.group(1)
            msg_name = match.group(2)
            interfaces.append(f"{package}/{msg_name}")

        return {
            "includes": messages,
            "interfaces": interfaces,
            "all_types": sorted(set(messages + interfaces)),
        }

    def extract_interface_summary(self, sdk_path: Path) -> dict[str, Any]:
        """
        Extract complete interface summary from SDK directory.

        Scans for .msg, .srv, .py, .hpp files to build complete interface map.

        Args:
            sdk_path: Path to SDK directory

        Returns:
            Comprehensive interface summary
        """
        summary = {
            "messages": [],
            "services": [],
            "topics": [],
            "message_types": set(),
        }

        # Find .msg files
        for msg_file in sdk_path.rglob("*.msg"):
            try:
                msg_def = self.parse_msg_file(msg_file)
                summary["messages"].append(msg_def.to_dict())
                summary["message_types"].add(f"{msg_def.package}/{msg_def.name}")
            except Exception as e:
                print(f"Warning: Could not parse {msg_file}: {e}")

        # Find .srv files
        for srv_file in sdk_path.rglob("*.srv"):
            # TODO: Parse service files
            pass

        # Find Python nodes
        for py_file in sdk_path.rglob("*.py"):
            try:
                node_info = self.parse_python_node(py_file)
                summary["topics"].extend(node_info["topics"])
                summary["message_types"].update(node_info["message_types"])
            except Exception as e:
                print(f"Warning: Could not parse {py_file}: {e}")

        # Find C++ headers
        for header_file in sdk_path.rglob("*.hpp"):
            try:
                header_info = self.parse_cpp_header(header_file)
                summary["message_types"].update(header_info["all_types"])
            except Exception as e:
                print(f"Warning: Could not parse {header_file}: {e}")

        summary["message_types"] = sorted(list(summary["message_types"]))
        return summary


# Example usage
if __name__ == "__main__":
    parser = ROS2InterfaceParser(ros2_available=False)

    # Test with a mock message
    test_msg = """# Standard metadata for higher-level stamped data types.
# This is generally used to communicate timestamped data
# in a particular coordinate frame.
builtin_interfaces/Time stamp
string frame_id
"""

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".msg", delete=False) as f:
        f.write(test_msg)
        f.flush()
        msg_path = Path(f.name)

    msg_def = parser.parse_msg_file(msg_path)
    print(f"Parsed: {msg_def.package}/{msg_def.name}")
    print(f"Fields: {len(msg_def.fields)}")
    for field in msg_def.fields:
        print(f"  - {field.name}: {field.type_str}")

    msg_path.unlink()
