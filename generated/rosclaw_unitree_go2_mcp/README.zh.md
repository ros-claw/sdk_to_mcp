# ROSClaw-Native Unitree unitree_go2 MCP 服务器

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-Protocol-purple.svg)](https://modelcontextprotocol.io/)

> 生产级 Unitree unitree_go2 MCP 服务器，深度集成 ROSClaw 具身智能操作系统
> **"教导一次，任意实体运行。共享技能，重塑现实。"**

[English Documentation](README.md) | [官方文档](https://docs.rosclaw.org/rosclaw_unitree_go2_mcp)

---

## 概述

`rosclaw_unitree_go2_mcp` 是一个 ROSClaw-Native MCP 服务器，它架起了大型语言模型（LLM）与 Unitree unitree_go2 机器人之间的桥梁。

### 核心特性

- **异步 ROS 2 动作**：使用 async/await 的非阻塞动作客户端
- **飞轮就绪响应**：结构化 JSON，支持数据飞轮自动采集
- **数字孪生防火墙**：真实执行前基于 MuJoCo 的安全验证
- **优雅抢占**：支持任务取消的活动任务跟踪
- **状态感知交互**：本地状态机防止无效操作
- **语义空间绑定**：TF2 集成用于语义机器人控制

---

## 安装

### 前置要求

- ROS 2 Humble
- Python 3.10+

### 从 PyPI 安装

```bash
pip install rosclaw_unitree_go2_mcp
```

### 从源码安装

```bash
git clone https://github.com/ros-claw/rosclaw_unitree_go2_mcp.git
cd rosclaw_unitree_go2_mcp
pip install -e ".[dev]"
```

---

## 快速开始

### 1. 启动 ROS 2

```bash
source /opt/ros/humble/setup.bash
ros2 launch your_robot_bringup robot.launch.py
```

### 2. 启动 MCP 服务器

```bash
rosclaw_unitree_go2_mcp
```

### 3. 配置 MCP 客户端

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

## ROSClaw-Native 六大标准

本 MCP 服务器实现了全部 6 大 ROSClaw-Native 标准：

1. ✅ **绝对异步** - 所有动作使用 async/await
2. ✅ **飞轮就绪 JSON** - 结构化响应支持数据飞轮
3. ✅ **防火墙集成** - `@mujoco_firewall` 确保物理安全
4. ✅ **优雅抢占** - 支持任务取消
5. ✅ **状态感知** - 防止无效并发操作
6. ✅ **语义空间绑定** - TF2 集成

---

## 许可证

Apache License 2.0 - 详见 [LICENSE](LICENSE)

---

<p align="center">
  <strong>ROSClaw - 具身智能操作系统</strong><br>
  <em>教导一次，任意实体运行。共享技能，重塑现实。</em>
</p>
