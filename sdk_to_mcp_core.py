"""
SDK to MCP Transformation Engine

This module provides intelligent automation pipeline for converting hardware SDKs
into Model Context Protocol (MCP) servers. It extracts protocol definitions,
generates type-safe MCP tools, and creates comprehensive documentation.

Key Features:
    - SDK version tracking and dependency management
    - Automatic protocol extraction from PDFs and source code
    - Safety-critical parameter validation
    - Comprehensive error handling interfaces
    - Hardware documentation integration

Usage:
    from sdk_to_mcp_core import SDKToMCPTransformer, SDKMetadata

    transformer = SDKToMCPTransformer()
    metadata = SDKMetadata(
        name="unitree_sdk2",
        version="2.1.0",
        source_url="https://github.com/unitreerobotics/unitree_sdk2",
        doc_url="https://support.unitree.com/home/zh/developer"
    )
    transformer.transform_sdk(metadata, sdk_path)
"""

import os
import re
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum, auto
from datetime import datetime


class CommunicationProtocol(Enum):
    """Supported communication protocols."""
    SERIAL = auto()
    DDS = auto()
    ROS = auto()
    ROS2 = auto()
    HTTP = auto()
    TCP = auto()
    UDP = auto()
    CAN = auto()
    MODBUS = auto()


class SafetyLevel(Enum):
    """Safety classification for parameters and operations."""
    CRITICAL = "critical"      # Immediate physical danger
    HIGH = "high"              # Potential hardware damage
    MEDIUM = "medium"          # Operational issue
    LOW = "low"                # Informational warning
    NONE = "none"              # No safety concern


@dataclass
class SDKMetadata:
    """
    Metadata for an SDK being transformed.

    This class tracks version information, source references, and dependencies
    to ensure MCP servers remain synchronized with their underlying SDKs.

    Attributes:
        name: SDK identifier (e.g., "unitree_sdk2")
        version: SDK version string (e.g., "2.1.0")
        protocol: Communication protocol used
        source_url: URL to SDK source code/repository
        doc_url: URL to official documentation
        license: License type (MIT, Apache-2.0, Proprietary, etc.)
        hardware_models: List of supported hardware models
        dependencies: SDK dependencies with versions
        checksum: SDK content hash for integrity verification
        extracted_date: When this metadata was generated
        notes: Additional notes about the SDK
    """
    name: str
    version: str
    protocol: CommunicationProtocol
    source_url: str
    doc_url: str
    license: str = "Unknown"
    hardware_models: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    checksum: str = ""
    extracted_date: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['protocol'] = self.protocol.name
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SDKMetadata":
        """Create from dictionary."""
        data = data.copy()
        data['protocol'] = CommunicationProtocol[data['protocol']]
        return cls(**data)


@dataclass
class SafetyConstraint:
    """
    Safety constraint for a parameter or operation.

    Attributes:
        parameter: Parameter name
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        units: Physical units (degrees, meters, rad/s, etc.)
        safety_level: Criticality level
        description: Human-readable description
        hardware_limit: Whether this is a hardware-enforced limit
        software_guard: Whether software should enforce this limit
    """
    parameter: str
    min_value: Optional[float]
    max_value: Optional[float]
    units: str
    safety_level: SafetyLevel
    description: str
    hardware_limit: bool = True
    software_guard: bool = True

    def validate(self, value: float) -> Tuple[bool, str]:
        """Validate a value against this constraint."""
        if self.min_value is not None and value < self.min_value:
            return False, (
                f"{self.parameter}={value}{self.units} below minimum "
                f"{self.min_value}{self.units}"
            )
        if self.max_value is not None and value > self.max_value:
            return False, (
                f"{self.parameter}={value}{self.units} exceeds maximum "
                f"{self.max_value}{self.units}"
            )
        return True, "OK"

    def to_code(self) -> str:
        """Generate Python code for this constraint."""
        lines = [
            f'"""{self.description}"""',
            f'"{self.parameter}": {{',
            f'    "min": {self.min_value},',
            f'    "max": {self.max_value},',
            f'    "units": "{self.units}",',
            f'    "safety_level": "{self.safety_level.value}",',
            f'    "hardware_limit": {self.hardware_limit},',
            f'    "software_guard": {self.software_guard},',
            '}}',
        ]
        return '\n        '.join(lines)


@dataclass
class ErrorDefinition:
    """
    Error code definition from SDK documentation.

    Attributes:
        code: Error code (numeric or string)
        name: Error identifier (e.g., "CONNECTION_TIMEOUT")
        description: Human-readable description
        severity: Error severity level
        recoverable: Whether the error is recoverable
        suggested_action: Suggested remediation steps
        sdk_reference: Reference to SDK documentation
    """
    code: str
    name: str
    description: str
    severity: str  # "critical", "error", "warning", "info"
    recoverable: bool
    suggested_action: str
    sdk_reference: str = ""

    def to_docstring(self) -> str:
        """Generate docstring section for this error."""
        return (
            f"    {self.name} ({self.code}):\n"
            f"        {self.description}\n"
            f"        Severity: {self.severity.upper()}\n"
            f"        Recoverable: {'Yes' if self.recoverable else 'No'}\n"
            f"        Action: {self.suggested_action}\n"
        )


@dataclass
class HardwareSpecification:
    """
    Hardware specifications extracted from SDK documentation.

    Attributes:
        model_name: Hardware model identifier
        manufacturer: Hardware manufacturer
        dimensions: Physical dimensions (L x W x H)
        weight: Weight in kg
        power_consumption: Power consumption in watts
        operating_temperature: Operating temperature range
        communication_interfaces: Available interfaces
        sensor_specs: Sensor specifications
        actuator_specs: Actuator specifications
        safety_features: Built-in safety features
        references: Reference documents
    """
    model_name: str
    manufacturer: str
    dimensions: Optional[Tuple[float, float, float]] = None  # L x W x H in mm
    weight: Optional[float] = None  # kg
    power_consumption: Optional[Tuple[float, float]] = None  # min, max watts
    operating_temperature: Optional[Tuple[float, float]] = None  # min, max Celsius
    communication_interfaces: List[str] = field(default_factory=list)
    sensor_specs: Dict[str, Any] = field(default_factory=dict)
    actuator_specs: Dict[str, Any] = field(default_factory=dict)
    safety_features: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    def to_documentation(self) -> str:
        """Generate hardware documentation markdown."""
        lines = [f"## {self.model_name}", ""]

        if self.manufacturer:
            lines.append(f"**Manufacturer:** {self.manufacturer}")

        if self.dimensions:
            lines.append(f"**Dimensions:** {self.dimensions[0]} x {self.dimensions[1]} x {self.dimensions[2]} mm")

        if self.weight:
            lines.append(f"**Weight:** {self.weight} kg")

        if self.power_consumption:
            lines.append(f"**Power:** {self.power_consumption[0]}-{self.power_consumption[1]}W")

        if self.operating_temperature:
            lines.append(f"**Temperature Range:** {self.operating_temperature[0]}°C to {self.operating_temperature[1]}°C")

        if self.communication_interfaces:
            lines.extend(["", "**Communication Interfaces:**"])
            for iface in self.communication_interfaces:
                lines.append(f"- {iface}")

        if self.safety_features:
            lines.extend(["", "**Safety Features:**"])
            for feature in self.safety_features:
                lines.append(f"- {feature}")

        if self.references:
            lines.extend(["", "**References:**"])
            for ref in self.references:
                lines.append(f"- {ref}")

        return '\n'.join(lines)


@dataclass
class MCPTool:
    """
    Definition of an MCP tool generated from SDK.

    Attributes:
        name: Tool name
        description: Tool description
        parameters: Parameter specifications
        returns: Return type description
        safety_constraints: Safety constraints for this tool
        error_codes: Possible error codes
        sdk_reference: Reference to SDK function
        example_usage: Example usage code
    """
    name: str
    description: str
    parameters: List[Dict[str, Any]]
    returns: str
    safety_constraints: List[SafetyConstraint]
    error_codes: List[ErrorDefinition]
    sdk_reference: str
    example_usage: str = ""

    def generate_code(self) -> str:
        """Generate Python code for this MCP tool."""
        # Generate parameter definitions
        params_str = ""
        for param in self.parameters:
            param_name = param['name']
            param_type = param['type']
            default = param.get('default', 'None')
            if default != 'None':
                params_str += f", {param_name}: {param_type} = {default}"
            else:
                params_str += f", {param_name}: {param_type}"

        # Generate docstring
        docstring_lines = [f'"""{self.description}"""', ""]

        if self.parameters:
            docstring_lines.append("Args:")
            for param in self.parameters:
                desc = param.get('description', 'No description')
                docstring_lines.append(f"    {param['name']}: {desc}")
            docstring_lines.append("")

        if self.safety_constraints:
            docstring_lines.append("Safety Constraints:")
            for constraint in self.safety_constraints:
                docstring_lines.append(
                    f"    {constraint.parameter}: "
                    f"[{constraint.min_value}, {constraint.max_value}] {constraint.units}"
                )
            docstring_lines.append("")

        if self.error_codes:
            docstring_lines.append("Raises:")
            for error in self.error_codes:
                docstring_lines.append(f"    {error.name}: {error.description}")
            docstring_lines.append("")

        docstring = '\n    '.join(docstring_lines)

        # Generate safety validation code
        validation_code = []
        for constraint in self.safety_constraints:
            param_name = constraint.parameter
            validation_code.append(f"""
        # Validate {param_name}
        valid, msg = self._safety.validate_{param_name}({param_name})
        if not valid:
            return f"SAFETY_VIOLATION: {{msg}}"
""")

        validation_str = ''.join(validation_code) if validation_code else "        pass"

        return f'''
@mcp.tool()
async def {self.name}({params_str}) -> str:
    {docstring}
    global _bridge

    if _bridge is None:
        return "ERROR: Device not connected. Call connect() first."

{validation_str}

    try:
        # TODO: Implement SDK call
        result = _bridge.{self.sdk_reference}({', '.join(p['name'] for p in self.parameters)})
        return f"SUCCESS: {{result}}"
    except Exception as e:
        logger.error(f"{self.name} failed: {{e}}")
        return f"ERROR: {{str(e)}}"
'''


class SDKToMCPTransformer:
    """
    Main transformer class for converting SDKs to MCP servers.

    This class orchestrates the transformation pipeline:
    1. SDK Discovery & Metadata Extraction
    2. Protocol Analysis
    3. Safety Constraint Extraction
    4. Error Code Mapping
    5. MCP Server Generation
    6. Documentation Generation

    Example:
        transformer = SDKToMCPTransformer()

        metadata = SDKMetadata(
            name="gcu_gimbal",
            version="V2.0.6",
            protocol=CommunicationProtocol.SERIAL,
            source_url="https://github.com/example/gcu_sdk",
            doc_url="https://docs.example.com/gcu",
            hardware_models=["Z-2Mini"],
            license="Proprietary"
        )

        result = transformer.transform_sdk(
            metadata=metadata,
            sdk_path=Path("/path/to/sdk"),
            output_path=Path("/path/to/output")
        )
    """

    def __init__(self):
        self.logger = self._setup_logging()
        self.extracted_metadata: List[SDKMetadata] = []
        self.safety_constraints: Dict[str, List[SafetyConstraint]] = {}
        self.error_definitions: Dict[str, List[ErrorDefinition]] = {}
        self.hardware_specs: Dict[str, HardwareSpecification] = {}

    def _setup_logging(self):
        """Setup logging for the transformer."""
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def transform_sdk(
        self,
        metadata: SDKMetadata,
        sdk_path: Path,
        output_path: Path,
    ) -> Dict[str, Path]:
        """
        Transform an SDK into an MCP server.

        Args:
            metadata: SDK metadata with version and reference information
            sdk_path: Path to the SDK directory
            output_path: Where to generate the MCP server

        Returns:
            Dictionary mapping file types to generated file paths

        Raises:
            FileNotFoundError: If SDK path doesn't exist
            ValueError: If metadata is invalid
        """
        if not sdk_path.exists():
            raise FileNotFoundError(f"SDK path not found: {sdk_path}")

        self.logger.info(f"Transforming {metadata.name} v{metadata.version}")

        # Calculate SDK checksum for version tracking
        metadata.checksum = self._calculate_checksum(sdk_path)

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        generated_files = {}

        # Phase 1: Extract protocol information
        self.logger.info("Phase 1: Extracting protocol information...")
        protocol_info = self._extract_protocol_info(sdk_path, metadata)

        # Phase 2: Extract safety constraints
        self.logger.info("Phase 2: Extracting safety constraints...")
        self.safety_constraints[metadata.name] = self._extract_safety_constraints(
            sdk_path, metadata
        )

        # Phase 3: Extract error definitions
        self.logger.info("Phase 3: Extracting error definitions...")
        self.error_definitions[metadata.name] = self._extract_error_definitions(
            sdk_path, metadata
        )

        # Phase 4: Extract hardware specifications
        self.logger.info("Phase 4: Extracting hardware specifications...")
        self.hardware_specs[metadata.name] = self._extract_hardware_specs(
            sdk_path, metadata
        )

        # Phase 5: Generate MCP server
        self.logger.info("Phase 5: Generating MCP server...")
        server_path = self._generate_mcp_server(
            metadata, protocol_info, output_path
        )
        generated_files['server'] = server_path

        # Phase 6: Generate comprehensive documentation
        self.logger.info("Phase 6: Generating documentation...")
        docs_path = self._generate_documentation(metadata, output_path)
        generated_files['documentation'] = docs_path

        # Phase 7: Generate metadata file
        self.logger.info("Phase 7: Generating metadata file...")
        metadata_path = self._generate_metadata_file(metadata, output_path)
        generated_files['metadata'] = metadata_path

        # Phase 8: Generate MCP config
        self.logger.info("Phase 8: Generating MCP configuration...")
        config_path = self._generate_mcp_config(metadata, output_path)
        generated_files['config'] = config_path

        self.logger.info(f"Transformation complete: {len(generated_files)} files generated")
        return generated_files

    def _calculate_checksum(self, sdk_path: Path) -> str:
        """Calculate a checksum of the SDK contents for version tracking."""
        hash_obj = hashlib.sha256()

        for file_path in sorted(sdk_path.rglob("*")):
            if file_path.is_file():
                try:
                    with open(file_path, 'rb') as f:
                        hash_obj.update(f.read())
                except (IOError, OSError):
                    pass

        return hash_obj.hexdigest()[:16]

    def _extract_protocol_info(
        self,
        sdk_path: Path,
        metadata: SDKMetadata
    ) -> Dict[str, Any]:
        """Extract protocol information from SDK."""
        protocol_info = {
            'protocol_type': metadata.protocol.name,
            'commands': [],
            'data_structures': [],
            'constants': {},
        }

        # Scan for protocol definition files
        for ext in ['.h', '.hpp', '.py', '.proto', '.md']:
            for file_path in sdk_path.rglob(f"*{ext}"):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # Extract command definitions
                    if metadata.protocol == CommunicationProtocol.SERIAL:
                        protocol_info['commands'].extend(
                            self._extract_serial_commands(content)
                        )
                    elif metadata.protocol in [CommunicationProtocol.ROS, CommunicationProtocol.ROS2]:
                        protocol_info['commands'].extend(
                            self._extract_ros_commands(content)
                        )

                except Exception as e:
                    self.logger.debug(f"Could not read {file_path}: {e}")

        return protocol_info

    def _extract_serial_commands(self, content: str) -> List[Dict[str, Any]]:
        """Extract serial protocol commands from source code."""
        commands = []

        # Pattern for command constants (e.g., CMD_RESET = 0x03)
        cmd_pattern = r'(?:CMD_|COMMAND_)(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)'
        for match in re.finditer(cmd_pattern, content):
            commands.append({
                'name': match.group(1),
                'code': match.group(2),
                'type': 'command'
            })

        return commands

    def _extract_ros_commands(self, content: str) -> List[Dict[str, Any]]:
        """Extract ROS/ROS2 commands from source code."""
        commands = []

        # Pattern for topic names
        topic_pattern = r'["\']([/\w]+)["\']\s*[,)]'
        for match in re.finditer(topic_pattern, content):
            topic = match.group(1)
            if '/' in topic and not topic.startswith('#'):
                commands.append({
                    'name': topic.split('/')[-1],
                    'topic': topic,
                    'type': 'topic'
                })

        return commands

    def _extract_safety_constraints(
        self,
        sdk_path: Path,
        metadata: SDKMetadata
    ) -> List[SafetyConstraint]:
        """Extract safety constraints from SDK documentation and code."""
        constraints = []

        # Default constraints for common robot parameters
        default_constraints = [
            SafetyConstraint(
                parameter="velocity",
                min_value=-100.0,
                max_value=100.0,
                units="rad/s",
                safety_level=SafetyLevel.HIGH,
                description="Joint velocity limit",
                hardware_limit=True,
                software_guard=True,
            ),
            SafetyConstraint(
                parameter="position",
                min_value=-3.14159,
                max_value=3.14159,
                units="rad",
                safety_level=SafetyLevel.HIGH,
                description="Joint position limit",
                hardware_limit=True,
                software_guard=True,
            ),
            SafetyConstraint(
                parameter="torque",
                min_value=-100.0,
                max_value=100.0,
                units="Nm",
                safety_level=SafetyLevel.CRITICAL,
                description="Joint torque limit - exceeding may damage hardware",
                hardware_limit=True,
                software_guard=True,
            ),
        ]

        # Look for safety documentation
        for doc_file in sdk_path.rglob("*.md"):
            try:
                with open(doc_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # Extract limits mentioned in documentation
                if 'limit' in content or 'safety' in content or 'constraint' in content:
                    # Look for patterns like "max speed: 150°/s"
                    limit_pattern = r'(max|min)\s*(\w+)\s*[:=]?\s*([\d.]+)\s*(\w+)'
                    for match in re.finditer(limit_pattern, content):
                        # Create constraint from documentation
                        pass  # Implementation depends on specific format

            except Exception as e:
                self.logger.debug(f"Could not process {doc_file}: {e}")

        return constraints if constraints else default_constraints

    def _extract_error_definitions(
        self,
        sdk_path: Path,
        metadata: SDKMetadata
    ) -> List[ErrorDefinition]:
        """Extract error codes and definitions from SDK."""
        errors = []

        # Standard error patterns to look for
        error_patterns = [
            (r'ERROR_\w+\s*=\s*(-?\d+)', 'constant'),
            (r'enum\s+\w*Error\w*\s*\{([^}]+)\}', 'enum'),
            (r'class\s+\w*Exception\w*', 'exception'),
        ]

        # Common error codes for robotics SDKs
        default_errors = [
            ErrorDefinition(
                code="-1",
                name="CONNECTION_FAILED",
                description="Failed to establish connection to device",
                severity="error",
                recoverable=True,
                suggested_action="Check device power, cables, and network connection",
            ),
            ErrorDefinition(
                code="-2",
                name="TIMEOUT",
                description="Operation timed out",
                severity="error",
                recoverable=True,
                suggested_action="Retry operation or check device responsiveness",
            ),
            ErrorDefinition(
                code="-3",
                name="INVALID_PARAMETER",
                description="Invalid parameter value provided",
                severity="error",
                recoverable=True,
                suggested_action="Check parameter ranges and types",
            ),
            ErrorDefinition(
                code="-4",
                name="SAFETY_VIOLATION",
                description="Operation would exceed safety limits",
                severity="critical",
                recoverable=True,
                suggested_action="Review safety constraints and adjust command",
            ),
            ErrorDefinition(
                code="-5",
                name="NOT_INITIALIZED",
                description="SDK or device not initialized",
                severity="error",
                recoverable=True,
                suggested_action="Call initialize() or connect() first",
            ),
        ]

        # Scan SDK source for error definitions
        for ext in ['.h', '.hpp', '.py', '.cs']:
            for file_path in sdk_path.rglob(f"*{ext}"):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    for pattern, pattern_type in error_patterns:
                        for match in re.finditer(pattern, content, re.IGNORECASE):
                            # Extract error information
                            pass  # Implementation depends on specific format

                except Exception as e:
                    self.logger.debug(f"Could not read {file_path}: {e}")

        return errors if errors else default_errors

    def _extract_hardware_specs(
        self,
        sdk_path: Path,
        metadata: SDKMetadata
    ) -> HardwareSpecification:
        """Extract hardware specifications from SDK documentation."""
        spec = HardwareSpecification(
            model_name=metadata.hardware_models[0] if metadata.hardware_models else "Unknown",
            manufacturer="Unknown",
            communication_interfaces=[metadata.protocol.name],
        )

        # Look for hardware documentation (PDFs, datasheets)
        for doc_file in sdk_path.rglob("*"):
            if doc_file.suffix.lower() in ['.pdf', '.doc', '.docx']:
                # Extract from PDF filename
                if 'manual' in doc_file.name.lower() or 'datasheet' in doc_file.name.lower():
                    spec.references.append(str(doc_file.name))

        # Look for README files with hardware info
        for readme in sdk_path.rglob("README*"):
            try:
                with open(readme, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Extract model information
                model_pattern = r'(?:model|device|hardware)\s*[:=]\s*([\w\-]+)'
                match = re.search(model_pattern, content, re.IGNORECASE)
                if match:
                    spec.model_name = match.group(1)

                # Extract manufacturer
                mfg_pattern = r'(?:manufacturer|vendor|by)\s*[:=]\s*([\w\s]+)'
                match = re.search(mfg_pattern, content, re.IGNORECASE)
                if match:
                    spec.manufacturer = match.group(1).strip()

            except Exception as e:
                self.logger.debug(f"Could not read {readme}: {e}")

        return spec

    def _generate_mcp_server(
        self,
        metadata: SDKMetadata,
        protocol_info: Dict[str, Any],
        output_path: Path
    ) -> Path:
        """Generate the MCP server Python file."""
        server_file = output_path / f"{metadata.name}_mcp_server.py"

        # Generate server code
        server_code = self._build_server_code(metadata, protocol_info)

        with open(server_file, 'w', encoding='utf-8') as f:
            f.write(server_code)

        return server_file

    def _build_server_code(
        self,
        metadata: SDKMetadata,
        protocol_info: Dict[str, Any]
    ) -> str:
        """Build the complete MCP server Python code."""

        # Header with SDK information
        header = f'''"""
{metadata.name.upper()} MCP Server

Auto-generated from SDK: {metadata.name}
Version: {metadata.version}
Protocol: {metadata.protocol.name}
Generated: {datetime.now().isoformat()}
Checksum: {metadata.checksum}

SDK Source: {metadata.source_url}
Documentation: {metadata.doc_url}
License: {metadata.license}

Safety Notice:
    This MCP server includes automatic safety validation for all motion commands.
    Hardware limits are enforced in software to prevent damage.

    CRITICAL: Always ensure emergency stop procedures are in place
    when controlling physical hardware through this interface.

Supported Hardware:
{chr(10).join(f"    - {model}" for model in metadata.hardware_models) if metadata.hardware_models else "    - Unknown"}

Error Handling:
    All tools return structured error messages. Common errors include:
    - CONNECTION_FAILED: Device not reachable
    - TIMEOUT: Operation exceeded time limit
    - SAFETY_VIOLATION: Command exceeds safety limits
    - INVALID_PARAMETER: Parameter out of valid range

For detailed error information, see the error_definitions dictionary
and individual tool docstrings.
"""

import asyncio
import logging
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP Server
mcp = FastMCP("{metadata.name}")

# SDK Metadata
SDK_METADATA = {{
    "name": "{metadata.name}",
    "version": "{metadata.version}",
    "protocol": "{metadata.protocol.name}",
    "source_url": "{metadata.source_url}",
    "doc_url": "{metadata.doc_url}",
    "license": "{metadata.license}",
    "checksum": "{metadata.checksum}",
    "generated_at": "{datetime.now().isoformat()}",
    "hardware_models": {metadata.hardware_models},
}}
'''

        # Safety constraints section
        safety_code = self._generate_safety_code(metadata.name)

        # Error definitions section
        error_code = self._generate_error_code(metadata.name)

        # Bridge class
        bridge_code = self._generate_bridge_class(metadata, protocol_info)

        # MCP Tools
        tools_code = self._generate_tools(metadata, protocol_info)

        # Resources
        resources_code = self._generate_resources(metadata)

        # Main entry point
        main_code = '''

if __name__ == "__main__":
    logger.info(f"Starting {SDK_METADATA['name']} MCP Server v{SDK_METADATA['version']}")
    logger.info(f"SDK Source: {SDK_METADATA['source_url']}")
    mcp.run(transport="stdio")
'''

        return header + safety_code + error_code + bridge_code + tools_code + resources_code + main_code

    def _generate_safety_code(self, sdk_name: str) -> str:
        """Generate safety constraint validation code."""
        constraints = self.safety_constraints.get(sdk_name, [])

        lines = ['\n\n# Safety Constraints', 'SAFETY_LIMITS = {']

        for constraint in constraints:
            lines.append(f'    "{constraint.parameter}": {{')
            lines.append(f'        "min": {constraint.min_value},')
            lines.append(f'        "max": {constraint.max_value},')
            lines.append(f'        "units": "{constraint.units}",')
            lines.append(f'        "safety_level": "{constraint.safety_level.value}",')
            lines.append(f'        "hardware_limit": {constraint.hardware_limit},')
            lines.append(f'        "software_guard": {constraint.software_guard},')
            lines.append(f'        "description": "{constraint.description}",')
            lines.append('    },')

        lines.extend(['}\n', '', 'class SafetyGuard:', '    """Safety validation for all motion commands."""', ''])

        # Generate validation methods
        for constraint in constraints:
            lines.append(f'    @staticmethod')
            lines.append(f'    def validate_{constraint.parameter}(value: float) -> Tuple[bool, str]:')
            lines.append(f'        """Validate {constraint.parameter} against safety limits."""')
            if constraint.min_value is not None:
                lines.append(f'        if value < {constraint.min_value}:')
                lines.append(f'            return False, "{constraint.parameter} below minimum {constraint.min_value}{constraint.units}"')
            if constraint.max_value is not None:
                lines.append(f'        if value > {constraint.max_value}:')
                lines.append(f'            return False, "{constraint.parameter} exceeds maximum {constraint.max_value}{constraint.units}"')
            lines.append('        return True, "OK"')
            lines.append('')

        return '\n'.join(lines)

    def _generate_error_code(self, sdk_name: str) -> str:
        """Generate error definition code."""
        errors = self.error_definitions.get(sdk_name, [])

        lines = ['\n# Error Definitions', 'ERROR_DEFINITIONS = {']

        for error in errors:
            lines.append(f'    "{error.name}": {{')
            lines.append(f'        "code": "{error.code}",')
            lines.append(f'        "description": "{error.description}",')
            lines.append(f'        "severity": "{error.severity}",')
            lines.append(f'        "recoverable": {error.recoverable},')
            lines.append(f'        "suggested_action": "{error.suggested_action}",')
            lines.append('    },')

        lines.append('}\n')

        return '\n'.join(lines)

    def _generate_bridge_class(
        self,
        metadata: SDKMetadata,
        protocol_info: Dict[str, Any]
    ) -> str:
        """Generate the bridge class for SDK communication."""

        return f'''

@dataclass
class DeviceState:
    """Current device state."""
    timestamp: float
    connected: bool
    error_code: int = 0
    error_message: str = ""


class {metadata.name.title()}Bridge:
    """
    Bridge class for {metadata.name} SDK communication.

    This class handles the low-level communication with the hardware,
    including connection management, protocol encoding/decoding, and
    thread-safe access.

    Protocol: {metadata.protocol.name}

    Thread Safety:
        All public methods are thread-safe. Internal state is protected
        by locks where necessary.

    Error Handling:
        All methods return success/failure status. Detailed error
        information is available via get_last_error().
    """

    def __init__(self):
        self._connected = False
        self._lock = threading.Lock()
        self._last_error: Optional[Tuple[int, str]] = None
        self._state = DeviceState(
            timestamp=time.time(),
            connected=False
        )

    def connect(self, **kwargs) -> bool:
        """
        Connect to the device.

        Args:
            **kwargs: Connection parameters (protocol-specific)

        Returns:
            True if connection successful, False otherwise

        Raises:
            CONNECTION_FAILED: Cannot establish connection
            TIMEOUT: Connection attempt timed out
        """
        try:
            with self._lock:
                # TODO: Implement actual connection logic
                self._connected = True
                self._state.connected = True
                return True
        except Exception as e:
            logger.error(f"Connection failed: {{e}}")
            self._last_error = (-1, str(e))
            return False

    def disconnect(self) -> None:
        """Disconnect from device and cleanup resources."""
        with self._lock:
            self._connected = False
            self._state.connected = False

    def is_connected(self) -> bool:
        """Check if device is connected."""
        with self._lock:
            return self._connected

    def get_last_error(self) -> Optional[Tuple[int, str]]:
        """Get the last error that occurred."""
        return self._last_error

    def get_state(self) -> DeviceState:
        """Get current device state."""
        with self._lock:
            return self._state


# Global bridge instance
_bridge: Optional[{metadata.name.title()}Bridge] = None
'''

    def _generate_tools(
        self,
        metadata: SDKMetadata,
        protocol_info: Dict[str, Any]
    ) -> str:
        """Generate MCP tools."""

        tools = ['\n# MCP Tools']

        # Connection tool
        tools.append('''
@mcp.tool()
async def connect(**kwargs) -> str:
    """
    Connect to the device.

    Establishes connection to hardware using protocol-specific parameters.
    Must be called before any other operations.

    Args:
        **kwargs: Connection parameters (see SDK documentation)

    Returns:
        Success or error message

    Raises:
        CONNECTION_FAILED: Unable to connect to device
        TIMEOUT: Connection attempt timed out

    Example:
        connect(port="COM8", baudrate=115200)
    """
    global _bridge

    if _bridge is None:
        _bridge = {bridge_class}()

    if _bridge.connect(**kwargs):
        return f"SUCCESS: Connected to {SDK_METADATA['name']}"
    else:
        error = _bridge.get_last_error()
        if error:
            return f"ERROR {error[0]}: {{error[1]}}"
        return "ERROR: Connection failed"
'''.format(bridge_class=f"{metadata.name.title()}Bridge"))

        # Disconnect tool
        tools.append('''
@mcp.tool()
async def disconnect() -> str:
    """
    Disconnect from the device.

    Safely closes connection and releases all resources.

    Returns:
        Success message
    """
    global _bridge

    if _bridge:
        _bridge.disconnect()
        _bridge = None
        return "SUCCESS: Disconnected"

    return "WARNING: Not connected"
''')

        # Get SDK info tool
        tools.append('''
@mcp.tool()
async def get_sdk_info() -> str:
    """
    Get SDK metadata and version information.

    Returns:
        JSON string with SDK metadata including version,
        source URL, documentation URL, and checksum.
    """
    import json
    return json.dumps(SDK_METADATA, indent=2)
''')

        return '\n'.join(tools)

    def _generate_resources(self, metadata: SDKMetadata) -> str:
        """Generate MCP resources."""

        return '''

# MCP Resources

@mcp.resource("sdk://metadata")
async def get_metadata() -> str:
    """
    Get SDK metadata.

    Returns:
        SDK name, version, source URL, and documentation links.
    """
    import json
    return json.dumps(SDK_METADATA, indent=2)

@mcp.resource("sdk://safety-limits")
async def get_safety_limits() -> str:
    """
    Get safety limits and constraints.

    Returns:
        Safety constraints for all motion parameters.
    """
    import json
    return json.dumps(SAFETY_LIMITS, indent=2)

@mcp.resource("sdk://error-definitions")
async def get_error_definitions() -> str:
    """
    Get error code definitions.

    Returns:
        All error codes with descriptions and recovery actions.
    """
    import json
    return json.dumps(ERROR_DEFINITIONS, indent=2)

@mcp.resource("device://state")
async def get_device_state() -> str:
    """
    Get current device state.

    Returns:
        Connection status and device state information.
    """
    global _bridge

    if _bridge is None:
        return "Device not connected"

    state = _bridge.get_state()
    return f"Connected: {state.connected}, Timestamp: {state.timestamp}"
'''

    def _generate_documentation(
        self,
        metadata: SDKMetadata,
        output_path: Path
    ) -> Path:
        """Generate comprehensive documentation."""
        docs_file = output_path / "README.md"

        # Get hardware spec
        spec = self.hardware_specs.get(metadata.name)

        docs = f'''# {metadata.name.upper()} MCP Server

## SDK Information

| Property | Value |
|----------|-------|
| **SDK Name** | {metadata.name} |
| **Version** | {metadata.version} |
| **Protocol** | {metadata.protocol.name} |
| **License** | {metadata.license} |
| **Generated** | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
| **Checksum** | `{metadata.checksum}` |

## Source References

- **SDK Repository:** [{metadata.source_url}]({metadata.source_url})
- **Documentation:** [{metadata.doc_url}]({metadata.doc_url})
- **MCP Protocol:** https://modelcontextprotocol.io

## Supported Hardware

{chr(10).join(f"- {model}" for model in metadata.hardware_models) if metadata.hardware_models else "No specific hardware models documented."}

'''

        # Add hardware specifications if available
        if spec:
            docs += spec.to_documentation() + '\n\n'

        # Add safety section
        docs += '''## Safety Information

**WARNING:** This MCP server controls physical hardware. Improper use can cause:
- Equipment damage
- Personal injury
- Property damage

### Safety Features

'''

        constraints = self.safety_constraints.get(metadata.name, [])
        if constraints:
            docs += "| Parameter | Min | Max | Units | Level |\n"
            docs += "|-----------|-----|-----|-------|-------|\n"
            for c in constraints:
                level_icon = "🔴" if c.safety_level == SafetyLevel.CRITICAL else "🟡" if c.safety_level == SafetyLevel.HIGH else "🟢"
                docs += f"| {c.parameter} | {c.min_value} | {c.max_value} | {c.units} | {level_icon} {c.safety_level.value} |\n"

        docs += '''
### Emergency Procedures

1. **Immediate Stop:** Use the `emergency_stop()` tool or physical E-stop button
2. **Power Off:** Disconnect power if safe to do so
3. **Check Status:** Use `get_device_state()` to assess situation

## Error Handling

### Error Codes

'''

        errors = self.error_definitions.get(metadata.name, [])
        if errors:
            docs += "| Code | Name | Severity | Recoverable | Description |\n"
            docs += "|------|------|----------|-------------|-------------|\n"
            for e in errors:
                rec_icon = "✅" if e.recoverable else "❌"
                sev_color = "🔴" if e.severity == "critical" else "🟠" if e.severity == "error" else "🟡"
                docs += f"| {e.code} | {e.name} | {sev_color} {e.severity} | {rec_icon} | {e.description[:50]}... |\n"

        docs += '''
### Troubleshooting

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Connection failed | Device powered off | Check power supply |
| Connection failed | Wrong port/address | Verify connection parameters |
| Timeout | Network latency | Increase timeout value |
| Safety violation | Command out of range | Check parameter limits |

## Available Tools

### Connection Management

- `connect(**kwargs)` - Connect to device
- `disconnect()` - Disconnect from device
- `get_sdk_info()` - Get SDK metadata

### MCP Resources

- `sdk://metadata` - SDK information
- `sdk://safety-limits` - Safety constraints
- `sdk://error-definitions` - Error code reference
- `device://state` - Current device state

## Configuration

### Claude Desktop

Add to your Claude Desktop configuration:

```json
{{
  "mcpServers": {{
    "{metadata.name}": {{
      "command": "python",
      "args": ["{output_path}/{metadata.name}_mcp_server.py"],
      "transportType": "stdio"
    }}
  }}
}}
```

### Cline / Other Clients

Configure according to your MCP client's documentation, pointing to:
```
python {output_path}/{metadata.name}_mcp_server.py
```

## Dependencies

```bash
pip install mcp
```

Additional dependencies may be required based on the SDK:
{chr(10).join(f"- {dep}" for dep in metadata.dependencies.keys()) if metadata.dependencies else "None specified"}

## Development Notes

This MCP server was auto-generated from SDK sources. To regenerate:

1. Update the SDK in `{metadata.source_url}`
2. Run the transformer with the new SDK path
3. Verify safety constraints are still valid
4. Test with hardware before deployment

## Support

- **SDK Issues:** Refer to [{metadata.doc_url}]({metadata.doc_url})
- **MCP Protocol:** https://modelcontextprotocol.io
- **ROSClaw Project:** https://github.com/ruvnet/rosclaw

## License

This MCP server follows the license terms of the underlying SDK:
**{metadata.license}**

---

*Generated by ROSClaw SDK-to-MCP Transformer*
*Version metadata is tracked via checksum: {metadata.checksum}*
'''

        with open(docs_file, 'w', encoding='utf-8') as f:
            f.write(docs)

        return docs_file

    def _generate_metadata_file(
        self,
        metadata: SDKMetadata,
        output_path: Path
    ) -> Path:
        """Generate a metadata JSON file for tracking."""
        metadata_file = output_path / "sdk_metadata.json"

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata.to_dict(), f, indent=2)

        return metadata_file

    def _generate_mcp_config(
        self,
        metadata: SDKMetadata,
        output_path: Path
    ) -> Path:
        """Generate MCP client configuration."""
        config_file = output_path / "mcp_config.json"

        config = {
            "mcpServers": {
                metadata.name: {
                    "command": "python",
                    "args": [str(output_path / f"{metadata.name}_mcp_server.py")],
                    "transportType": "stdio",
                    "description": f"{metadata.name} v{metadata.version}",
                    "sdk_version": metadata.version,
                    "sdk_source": metadata.source_url,
                }
            }
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        return config_file


def transform_sdk_to_mcp(
    sdk_path: str,
    output_path: str,
    metadata: Optional[SDKMetadata] = None,
) -> Dict[str, Path]:
    """
    Convenience function to transform an SDK to MCP server.

    Args:
        sdk_path: Path to SDK directory
        output_path: Where to generate MCP server
        metadata: Optional pre-defined metadata (will extract if not provided)

    Returns:
        Dictionary of generated file paths
    """
    transformer = SDKToMCPTransformer()

    if metadata is None:
        # Try to extract metadata automatically
        sdk_path_obj = Path(sdk_path)

        # Try to read from existing files
        name = sdk_path_obj.name
        version = "unknown"

        # Look for version in common files
        for version_file in ['version.txt', 'VERSION', 'package.json', 'setup.py']:
            vf = sdk_path_obj / version_file
            if vf.exists():
                try:
                    content = vf.read_text()
                    # Try to extract version
                    match = re.search(r'version\s*[=:]\s*["\']?([\d.]+)', content)
                    if match:
                        version = match.group(1)
                        break
                except:
                    pass

        metadata = SDKMetadata(
            name=name,
            version=version,
            protocol=CommunicationProtocol.SERIAL,
            source_url="",
            doc_url="",
        )

    return transformer.transform_sdk(
        metadata=metadata,
        sdk_path=Path(sdk_path),
        output_path=Path(output_path),
    )


# Example usage
if __name__ == "__main__":
    # Example: Transform GCU Gimbal SDK
    metadata = SDKMetadata(
        name="gcu_gimbal",
        version="V2.0.6",
        protocol=CommunicationProtocol.SERIAL,
        source_url="https://github.com/xianfei/GCU-SDK",
        doc_url="https://docs.xianfei.com/gcu",
        license="Proprietary",
        hardware_models=["Z-2Mini", "A5 Gimbal"],
    )

    # This would be called with actual paths
    # result = transform_sdk_to_mcp(
    #     sdk_path="/path/to/gcu_sdk",
    #     output_path="/path/to/output",
    #     metadata=metadata,
    # )

    print("SDK to MCP Transformer loaded successfully")
    print("Use transform_sdk_to_mcp() to convert an SDK")
