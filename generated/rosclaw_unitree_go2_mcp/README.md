# ROSClaw-Native Unitree unitree_go2 MCP Server

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-Protocol-purple.svg)](https://modelcontextprotocol.io/)

> Production-grade MCP server for Unitree unitree_go2 with ROSClaw OS integration.
> **"Teach Once, Embody Anywhere. Share Skills, Shape Reality."**

[中文文档](README.zh.md) | [Documentation](https://docs.rosclaw.org/rosclaw_unitree_go2_mcp)

---

## Overview

`rosclaw_unitree_go2_mcp` is a ROSClaw-Native MCP server that bridges Large Language Models (LLMs) with Unitree unitree_go2 robots.

### Key Features

- **Asynchronous ROS 2 Actions**: Non-blocking action clients with async/await
- **Flywheel-Ready Responses**: Structured JSON for Data Flywheel ingestion
- **Digital Twin Firewall**: MuJoCo-based safety validation
- **Graceful Preemption**: Active task tracking with cancel support
- **State-Aware Affordance**: Local state machine prevents invalid operations
- **Semantic Spatial Binding**: TF2 integration for semantic robot control

---

## Installation

### Prerequisites

- ROS 2 Humble
- Python 3.10+

### Install from PyPI

```bash
pip install rosclaw_unitree_go2_mcp
```

### Install from Source

```bash
git clone https://github.com/ros-claw/rosclaw_unitree_go2_mcp.git
cd rosclaw_unitree_go2_mcp
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Start ROS 2

```bash
source /opt/ros/humble/setup.bash
ros2 launch your_robot_bringup robot.launch.py
```

### 2. Start the MCP Server

```bash
rosclaw_unitree_go2_mcp
```

### 3. Configure MCP Client

```json
{
  "mcpServers": {
    "rosclaw_unitree_go2_mcp": {
      "command": "rosclaw_unitree_go2_mcp",
      "transportType": "stdio"
    }
  }
}
```

---

## ROSClaw-Native Standards

This MCP Server implements all 6 ROSClaw-Native Standards:

1. ✅ **Absolute Async** - All actions use async/await
2. ✅ **Flywheel-Ready JSON** - Structured responses for Data Flywheel
3. ✅ **Firewall Integration** - `@mujoco_firewall` for physical safety
4. ✅ **Graceful Preemption** - Task cancellation support
5. ✅ **State-Aware** - Prevents invalid concurrent operations
6. ✅ **Semantic Spatial Binding** - TF2 integration

---

## License

Apache License 2.0 - See [LICENSE](LICENSE)

---

<p align="center">
  <strong>ROSClaw - Embodied Intelligence Operating System</strong><br>
  <em>Teach Once, Embody Anywhere. Share Skills, Shape Reality.</em>
</p>
