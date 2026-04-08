# SDK-to-MCP: Hardware SDK to MCP Server Converter

🌐 **English** | [中文](./README.zh.md)

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](LICENSE)

**Transform any hardware SDK or protocol document into a standardized MCP Server**

</div>

## 🎯 Overview

**sdk-to-mcp** is an intelligent automation pipeline that converts heterogeneous hardware interfaces (PDF protocols, C++/Python SDKs, ROS interfaces) into standardized Model Context Protocol (MCP) servers. This enables AI assistants like Claude to control physical robots and devices through natural language.

### Key Features

- 🔌 **Multi-Protocol Support**: Serial, DDS, ROS/ROS2, HTTP/REST
- 🤖 **AI-Powered Analysis**: LLM-driven protocol extraction from PDFs and code
- 🛡️ **Built-in Safety**: Automatic safety guards and limit validation
- ⚡ **Code Generation**: Jinja2-based template engine for MCP server generation
- ✅ **Auto-Validation**: Automatic syntax checking and error correction
- 🔧 **Production Ready**: Full type hints, async support, comprehensive error handling
- 📊 **SDK Version Tracking**: Automatic checksum generation for version verification

---

## 📚 SDK References and Sources

This project maintains strict version tracking for all integrated SDKs. Each MCP server generated includes:
- **SDK Version**: Exact version number of the source SDK
- **Source URL**: Link to official repository or documentation
- **Checksum**: SHA256 hash for integrity verification
- **License**: Compliance with original SDK licensing terms

### Supported SDKs

| SDK Name | Version | Protocol | Source Repository | Documentation | License |
|----------|---------|----------|-------------------|---------------|---------|
| **Unitree SDK2** | 2.1.0+ | DDS | [unitreerobotics/unitree_sdk2](https://github.com/unitreerobotics/unitree_sdk2) | [Unitree Docs](https://support.unitree.com/home/zh/developer) | BSD-3-Clause |
| **GCU Gimbal SDK** | V2.0.6 | Serial | Proprietary | [GCU Protocol PDF](./sdk/xianfei/GCU私有通信协议-XF(A5)V2.0.6.pdf) | Proprietary |
| **Universal Robots ROS2 Driver** | 2.4.0+ | ROS2 | [UniversalRobots/Universal_Robots_ROS2_Driver](https://github.com/UniversalRobots/Universal_Robots_ROS2_Driver) | [ROS2 Driver Docs](https://docs.universal-robots.com/Universal_Robots_ROS2_Documentation/doc/ur_robot_driver/ur_robot_driver/doc/index.html) | Apache-2.0 |
| **ur_rtde** | 1.0.0+ | TCP | [sdurw/ur_rtde](https://gitlab.com/sdurobotics/ur_rtde) | [ur_rtde Docs](https://sdurobotics.gitlab.io/ur_rtde/) | MIT |
| **Inspire Robots SDK** | Latest | Serial | [inspire-robotics/sdk](https://github.com/inspire-robotics) | Proprietary | Proprietary |
| **Paxini SDK** | Latest | DDS/Serial | Proprietary | Proprietary | Proprietary |

### Hardware Documentation

| Hardware | Model | Manufacturer | Key Specs | Documentation |
|----------|-------|--------------|-----------|---------------|
| **Unitree G1** | G1-23D/43D | Unitree Robotics | 23/43 DOF, 35kg, 2.5h runtime | [User Manual](https://support.unitree.com/home/zh/G1_developer) |
| **Unitree Go2** | Go2-Air/Pro/EDU | Unitree Robotics | 12 DOF quadruped, 15kg | [Go2 Docs](https://support.unitree.com/home/zh/Go2_developer) |
| **Unitree H1** | H1 | Unitree Robotics | 19 DOF humanoid, 47kg | [H1 Docs](https://support.unitree.com/home/zh/H1_developer) |
| **GCU Z-2Mini** | Z-2Mini | Xianfei Tech | 3-axis gimbal, ±150°/s, 115200 baud | [User Manual](./sdk/xianfei/Z-2Mini用户手册-XF(A5)V1.4.pdf) |
| **UR5e** | UR5e | Universal Robots | 6 DOF arm, 5kg payload, ±360° joints | [UR5e Specs](https://www.universal-robots.com/products/ur5-robot/) |
| **Inspire Hand** | RH56DFX/RH56BFX | Inspire Robots | 6 DOF dexterous hand | Proprietary |

---

## 📁 Repository Structure

```
sdk_to_mcp/
├── sdk_to_mcp_core.py          # Core transformation engine (enhanced)
│                               # - SDK version tracking
│                               # - Safety constraint extraction
│                               # - Error code mapping
│                               # - Hardware spec extraction
│
├── SKILL.md                    # Skill definition for AI agents
│
├── example/                    # Example MCP servers (production-ready)
│   ├── ros-mcp-server/         # Full-featured ROS MCP server
│   │   └── ros_mcp/            # Source: ROS/ROS2
│   ├── ros2-mcp-server/        # ROS 2 native MCP server
│   │   └── Source: ROS 2 Humble/Jazzy
│   ├── unitree-go2-mcp-server/ # Unitree Go2 robot MCP
│   │   └── Source: unitree_sdk2
│   └── robot_MCP/              # SO-ARM100/LeKiwi robot MCP
│       └── Source: LeRobot
│
├── sdk/                        # Hardware SDKs (version-pinned)
│   ├── xianfei/                # GCU Gimbal SDK V2.0.6
│   │   ├── GCU私有通信协议-XF(A5)V2.0.6.pdf
│   │   ├── Z-2Mini用户手册-XF(A5)V1.4.pdf
│   │   └── gcu_gimbal_control.py
│   │
│   ├── unitree_sdk2/           # Unitree SDK2 (latest)
│   │   ├── README.md
│   │   └── examples/           # G1, Go2, H1, B2 examples
│   │
│   ├── Universal_Robots_ROS2_Driver/  # UR ROS2 Driver
│   │   └── Source: GitHub main
│   │
│   ├── ur_rtde/                # ur_rtde C++ library
│   │   ├── doc/                # API documentation
│   │   └── examples/           # Python/C++ examples
│   │
│   ├── inspire_robots/         # Inspire hand SDK
│   │   └── Source: Proprietary
│   │
│   └── paxini/                 # Paxini tactile sensor SDK
│       └── Source: Proprietary
│
├── generated/                  # Generated MCP servers
│   ├── gcu_gimbal_mcp_server.py  # GCU Gimbal MCP Server
│   │                               # SDK Version: V2.0.6
│   │                               # Checksum: [auto-generated]
│   ├── sdk_metadata.json       # Version tracking metadata
│   └── README.md               # Generated server usage guide
│
└── README.md                   # This file
```

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/ros-claw/sdk_to_mcp.git
cd sdk_to_mcp

# Install dependencies
pip install mcp pyserial

# For ROS2 support
pip install rclpy

# For DDS support (Unitree)
pip install cyclonedds
```

### Transform an SDK

```python
from sdk_to_mcp_core import SDKToMCPTransformer, SDKMetadata, CommunicationProtocol

# Initialize transformer
transformer = SDKToMCPTransformer()

# Define SDK metadata with version tracking
metadata = SDKMetadata(
    name="gcu_gimbal",
    version="V2.0.6",
    protocol=CommunicationProtocol.SERIAL,
    source_url="https://github.com/xianfei/GCU-SDK",
    doc_url="https://docs.xianfei.com/gcu",
    license="Proprietary",
    hardware_models=["Z-2Mini", "A5 Gimbal"],
)

# Transform SDK to MCP server
result = transformer.transform_sdk(
    metadata=metadata,
    sdk_path=Path("./sdk/xianfei"),
    output_path=Path("./generated/gcu_gimbal")
)

print(f"Generated files: {result}")
```

### Generated Output Structure

Each transformation generates:

```
generated/{sdk_name}/
├── {sdk_name}_mcp_server.py   # Main MCP server with:
│                               # - SDK version metadata
│                               # - Safety constraint validation
│                               # - Error code handling
│                               # - Hardware-specific bridge class
│
├── README.md                   # Comprehensive documentation:
│                               # - SDK version info
│                               # - Source references
│                               # - Safety limits table
│                               # - Error code reference
│                               # - Troubleshooting guide
│
├── sdk_metadata.json           # Machine-readable metadata:
│                               # - name, version, checksum
│                               # - source_url, doc_url
│                               # - hardware_models
│
└── mcp_config.json             # MCP client configuration
```

---

## 🏗️ Architecture

The enhanced SDK-to-MCP pipeline consists of 8 phases:

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: SDK Discovery & Metadata Extraction               │
│  - SDK version detection (package.json, setup.py, etc.)     │
│  - Source URL extraction                                    │
│  - Checksum calculation for integrity tracking              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Protocol Analysis                                 │
│  - PDF protocol extraction (GCU, proprietary)               │
│  - Code parsing (ROS/DDS topics, services)                  │
│  - Command mapping and data structure extraction            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: Safety Constraint Extraction                      │
│  - Hardware limit detection from docs                       │
│  - Velocity/position/torque limits                          │
│  - Safety level classification (CRITICAL/HIGH/MEDIUM)       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Error Code Mapping                                │
│  - Extract error codes from SDK headers                     │
│  - Map error names to descriptions                          │
│  - Define recovery actions                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: Hardware Specification                            │
│  - Extract hardware specs from datasheets                   │
│  - Dimensions, weight, power consumption                    │
│  - Communication interfaces                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 6: MCP Server Generation                             │
│  - Generate bridge class with protocol implementation       │
│  - Create MCP tools with safety validation                  │
│  - Add comprehensive docstrings                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 7: Documentation Generation                          │
│  - Generate README with version info                        │
│  - Create safety limits table                               │
│  - Document error codes and troubleshooting                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 8: Metadata Export                                   │
│  - Export sdk_metadata.json                                 │
│  - Generate mcp_config.json                                 │
│  - Verify checksums match                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Safety Features

All generated MCP servers include comprehensive safety features:

### Safety Constraint System

```python
# Example from generated GCU Gimbal MCP server
SAFETY_LIMITS = {
    "pitch_speed": {
        "min": -150.0,
        "max": 150.0,
        "units": "°/s",
        "safety_level": "high",
        "hardware_limit": True,
        "software_guard": True,
        "description": "Pitch rotation speed limit",
    },
    "pitch_angle": {
        "min": -90.0,
        "max": 90.0,
        "units": "°",
        "safety_level": "critical",
        "hardware_limit": True,
        "software_guard": True,
        "description": "Pitch angle limit - exceeding may damage gimbal",
    },
}
```

### Automatic Validation

```python
@mcp.tool()
async def rotate(pitch_speed: float = 0, yaw_speed: float = 0) -> str:
    """
    Rotate the gimbal.

    Safety Constraints:
        pitch_speed: [-150, 150] °/s
        yaw_speed: [-150, 150] °/s
    """
    # Automatic validation
    valid, msg = SafetyGuard.validate_pitch_speed(pitch_speed)
    if not valid:
        return f"SAFETY_VIOLATION: {msg}"
    ...
```

### Safety Levels

| Level | Icon | Description | Example |
|-------|------|-------------|---------|
| **CRITICAL** | 🔴 | Immediate physical danger | Exceeding joint torque limits |
| **HIGH** | 🟠 | Potential hardware damage | Velocity limits, collision risk |
| **MEDIUM** | 🟡 | Operational issue | Out-of-range setpoints |
| **LOW** | 🟢 | Informational warning | Non-optimal configurations |

### Emergency Procedures

All generated servers document emergency procedures:

1. **Immediate Stop**: Use `emergency_stop()` tool or physical E-stop
2. **Power Off**: Disconnect power if safe to do so
3. **Check Status**: Use `get_device_state()` to assess situation

---

## ⚠️ Error Handling

### Error Code System

Generated MCP servers include comprehensive error definitions:

```python
ERROR_DEFINITIONS = {
    "CONNECTION_FAILED": {
        "code": "-1",
        "description": "Failed to establish connection to device",
        "severity": "error",
        "recoverable": True,
        "suggested_action": "Check device power, cables, and network connection",
    },
    "SAFETY_VIOLATION": {
        "code": "-4",
        "description": "Operation would exceed safety limits",
        "severity": "critical",
        "recoverable": True,
        "suggested_action": "Review safety constraints and adjust command",
    },
}
```

### Error Code Reference

| Code | Name | Severity | Recoverable | Common Causes |
|------|------|----------|-------------|---------------|
| -1 | CONNECTION_FAILED | 🟠 error | ✅ | Device powered off, wrong port |
| -2 | TIMEOUT | 🟠 error | ✅ | Network latency, device unresponsive |
| -3 | INVALID_PARAMETER | 🟠 error | ✅ | Out-of-range values, wrong type |
| -4 | SAFETY_VIOLATION | 🔴 critical | ✅ | Exceeding velocity/position limits |
| -5 | NOT_INITIALIZED | 🟠 error | ✅ | Missing `connect()` call |
| -6 | PROTOCOL_MISMATCH | 🟠 error | ❌ | Wrong SDK version, incompatible hardware |
| -7 | HARDWARE_FAULT | 🔴 critical | ❌ | Motor fault, encoder error |

### Troubleshooting Guide

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Connection failed | Device powered off | Check power supply and switches |
| Connection failed | Wrong port/address | Verify COM port or IP address |
| Connection failed | Permission denied | Run with sudo (Linux) or admin (Windows) |
| Timeout | Network latency | Increase timeout parameter |
| Timeout | Device busy | Check for other connected clients |
| Safety violation | Command out of range | Check parameter limits in documentation |
| Safety violation | Wrong units | Verify units (degrees vs radians) |
| Protocol mismatch | Wrong SDK version | Update to matching SDK version |
| Hardware fault | Overheating | Allow cooling period |
| Hardware fault | Mechanical jam | Power off and check mechanics |

---

## 🔧 MCP Server Configuration

### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "gcu-gimbal": {
      "command": "python",
      "args": ["/path/to/gcu_gimbal_mcp_server.py"],
      "transportType": "stdio",
      "description": "GCU Gimbal V2.0.6",
      "sdk_version": "V2.0.6",
      "sdk_source": "https://github.com/xianfei/GCU-SDK"
    },
    "unitree-g1": {
      "command": "python",
      "args": ["/path/to/unitree_g1_mcp_server.py"],
      "transportType": "stdio",
      "description": "Unitree G1 via SDK2",
      "sdk_version": "2.1.0",
      "sdk_source": "https://github.com/unitreerobotics/unitree_sdk2"
    }
  }
}
```

Configuration file locations:
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`
- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Cline / VS Code

```json
{
  "mcpServers": {
    "ros-ur5": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/ros-mcp-server",
        "run",
        "python",
        "-m",
        "ros_mcp.main"
      ],
      "transportType": "stdio",
      "sdk_version": "2.4.0",
      "sdk_source": "https://github.com/UniversalRobots/Universal_Robots_ROS2_Driver"
    }
  }
}
```

---

## 💡 Usage Examples

### Example 1: GCU Gimbal Control

```python
# Connect to gimbal
await connect(port="COM8", baudrate=115200)

# Set working mode
await set_mode("angle_lock")  # Options: angle_lock, follow, euler, fpv

# Rotate with safety limits enforced
await rotate(pitch_speed=30, yaw_speed=0, duration=2)

# Take photo
await take_photo(camera=1)

# Get status
status = await get_gimbal_status()
```

**Safety Note**: All rotation commands are automatically limited to ±150°/s. Exceeding these limits returns `SAFETY_VIOLATION` error.

### Example 2: Unitree G1 Humanoid

```python
# Connect to robot
await connect()

# Stand up
await set_pose("stand")

# Walk forward
await move(linear_x=0.5, duration=5.0)

# Wave
await play_motion("wave_hand")
```

**Safety Note**: Maximum linear velocity is 1.0 m/s. Emergency stop (`L1+R1`) is always active on physical controller.

### Example 3: UR5e Arm Control

```python
# Connect via ROS2
await connect(robot_ip="192.168.1.100")

# Move to pose
await move_joints([0, -1.57, 1.57, 0, 0, 0])

# Linear motion
await move_linear(position=[0.3, 0.2, 0.4])
```

**Safety Note**: Joint limits are ±360° but speed limits vary by joint. See `SAFETY_LIMITS` resource for details.

---

## 📊 Version Tracking

Each generated MCP server includes version tracking:

### SDK Metadata Format

```json
{
  "name": "gcu_gimbal",
  "version": "V2.0.6",
  "protocol": "SERIAL",
  "source_url": "https://github.com/xianfei/GCU-SDK",
  "doc_url": "https://docs.xianfei.com/gcu",
  "license": "Proprietary",
  "hardware_models": ["Z-2Mini", "A5 Gimbal"],
  "checksum": "a1b2c3d4e5f6...",
  "extracted_date": "2026-04-07T10:30:00",
  "notes": "Generated from PDF protocol V2.0.6"
}
```

### Checksum Verification

To verify SDK integrity:

```python
from sdk_to_mcp_core import SDKToMCPTransformer

transformer = SDKToMCPTransformer()
current_checksum = transformer._calculate_checksum(sdk_path)

# Compare with stored checksum
if current_checksum == stored_checksum:
    print("✓ SDK integrity verified")
else:
    print("⚠ SDK has changed - regeneration recommended")
```

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Areas for Contribution

- New protocol templates (CAN, Modbus, MQTT, EtherCAT)
- Additional hardware examples
- Improved SDK version detection
- Better PDF extraction for non-English docs
- Enhanced safety constraint detection
- Additional error code databases

---

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

**Note**: Generated MCP servers inherit the license of their underlying SDKs. Always verify SDK licensing before distribution.

| SDK | License | Commercial Use |
|-----|---------|----------------|
| Unitree SDK2 | BSD-3-Clause | ✅ Allowed |
| GCU Gimbal | Proprietary | ❌ Restricted |
| UR ROS2 Driver | Apache-2.0 | ✅ Allowed |
| ur_rtde | MIT | ✅ Allowed |

---

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP standard by Anthropic
- [FastMCP](https://github.com/jlowin/fastmcp) - Python MCP framework
- [ROS](https://ros.org/) - Robot Operating System
- [Unitree Robotics](https://unitree.com/) - Quadruped and humanoid robots
- [Universal Robots](https://www.universal-robots.com/) - Collaborative robot arms

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/ros-claw/sdk_to_mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ros-claw/sdk_to_mcp/discussions)
- **Documentation**: This README and generated server READMEs

---

<div align="center">

**Made with ❤️ for the ROS and AI communities**

*[ROSClaw Project](https://github.com/ros-claw) - Agent-Agnostic Embodied Intelligence Middleware*

</div>
