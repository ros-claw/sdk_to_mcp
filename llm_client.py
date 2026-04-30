#!/usr/bin/env python3
"""
🧠 LLM Client for Agentic Compiler

Supports multiple LLM providers:
- DeepSeek (recommended for coding tasks)
- OpenAI GPT-4
- Anthropic Claude
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class LLMResponse:
    """Structured LLM response"""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate text from prompts"""
        pass


class DeepSeekClient(BaseLLMClient):
    """
    DeepSeek LLM Client

    API Docs: https://platform.deepseek.com/
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-coder"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API key required. Set DEEPSEEK_API_KEY env var.")

        self.model = model
        self.base_url = "https://api.deepseek.com/v1"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Generate code using DeepSeek API"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Clean up code blocks if present
            if "```python" in content:
                content = content.split("```python")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return content

        except requests.exceptions.RequestException as e:
            print(f"[LLM] ❌ DeepSeek API error: {e}")
            raise


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT Client"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var.")

        self.model = model

        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package required. Install: pip install openai")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Generate code using OpenAI API"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content

            # Clean up code blocks
            if "```python" in content:
                content = content.split("```python")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return content

        except Exception as e:
            print(f"[LLM] ❌ OpenAI API error: {e}")
            raise


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM Client for testing

    Returns placeholder code without calling external APIs
    """

    def __init__(self, fail_first_n: int = 0):
        """
        Args:
            fail_first_n: Number of first calls to return incomplete code
                         (to test Critic self-healing)
        """
        self.call_count = 0
        self.fail_first_n = fail_first_n

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate mock code"""
        self.call_count += 1

        # Simulate first attempt failing (missing standards)
        if self.call_count <= self.fail_first_n:
            print(f"[MOCK LLM] 🎭 Simulating incomplete generation (attempt {self.call_count})")
            return self._generate_incomplete_code()

        print(f"[MOCK LLM] ✅ Generating complete code (attempt {self.call_count})")
        return self._generate_complete_code()

    def _generate_incomplete_code(self) -> str:
        """Generate code missing some standards (for testing)"""
        return '''
#!/usr/bin/env python3
"""Incomplete MCP Server - Missing some standards"""

def move_robot(x, y):
    """Move robot - NOT ASYNC, NO FIREWALL"""
    print(f"Moving to {x}, {y}")
    return {"success": True}
'''

    def _generate_complete_code(self) -> str:
        """Generate complete ROSClaw-Native code"""
        return '''
#!/usr/bin/env python3
"""ROSClaw-Native MCP Server"""

from __future__ import annotations
import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from mcp.server.fastmcp import FastMCP
from rosclaw.firewall.decorator import mujoco_firewall, SafetyLevel

class ActionStatus(Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"

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
        return json.dumps({
            "status": self.status.value,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "semantic_goal": self.semantic_goal,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error": {"code": self.error_code, "message": self.error_message},
            "safety": {"firewall_validated": self.firewall_validated, "violations": self.safety_violations}
        }, indent=2)

@dataclass
class RobotState:
    is_moving: bool = False
    is_standing: bool = False
    last_action_id: Optional[str] = None

class ROSClawTestClient:
    def __init__(self):
        self.state = RobotState()
        self._active_tasks: Dict[str, Any] = {}
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

    async def _ros_spin(self) -> None:
        while True:
            await asyncio.sleep(0.001)

    async def cancel_action(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self._active_tasks:
            return {"success": False, "error": f"No active action with ID: {task_id}"}
        goal_handle = self._active_tasks[task_id]
        try:
            cancel_future = goal_handle.cancel_goal_async()
            cancel_result = await self._await_future(cancel_future)
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            return {"success": True, "message": f"Action {task_id} canceled"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _await_future(self, future: Any, timeout: float = 30.0) -> Any:
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        while not future.done():
            if loop.time() - start_time > timeout:
                raise TimeoutError(f"Future timeout after {timeout}s")
            await asyncio.sleep(0.01)
        return future.result()

mcp = FastMCP("rosclaw-test")
client: Optional[ROSClawTestClient] = None

@mcp.on_startup
async def on_startup():
    global client
    client = ROSClawTestClient()
    await client.start()

@mcp.on_shutdown
async def on_shutdown():
    global client
    if client:
        await client.stop()

@mcp.tool()
async def get_state() -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})
    return json.dumps({
        "is_moving": client.state.is_moving,
        "is_standing": client.state.is_standing,
    })

@mcp.tool()
@mujoco_firewall(safety_level=SafetyLevel.STRICT)
async def move_robot(x: float, y: float) -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})

    if client.state.is_moving:
        return ActionResult(
            status=ActionStatus.REJECTED,
            action_id=str(uuid.uuid4()),
            action_type="move_robot",
            semantic_goal=f"Move to ({x}, {y})",
            timestamp_start=time.time(),
            error_code="STATE_REJECTED",
            error_message="Robot is already moving"
        ).to_json()

    await asyncio.sleep(0.1)

    result = ActionResult(
        status=ActionStatus.SUCCEEDED,
        action_id=str(uuid.uuid4()),
        action_type="move_robot",
        semantic_goal=f"Move to ({x}, {y})",
        timestamp_start=time.time(),
        timestamp_end=time.time(),
        duration_seconds=0.1,
        success=True,
        firewall_validated=True
    )
    return result.to_json()

@mcp.tool()
async def cancel_action_tool(task_id: str) -> str:
    if not client:
        return json.dumps({"error": "Client not initialized"})
    result = await client.cancel_action(task_id)
    return json.dumps(result)
'''


def create_llm_client(provider: str = "mock", **kwargs) -> BaseLLMClient:
    """
    Factory function to create LLM client

    Args:
        provider: "deepseek", "openai", or "mock"
        **kwargs: Provider-specific arguments
    """
    if provider == "deepseek":
        return DeepSeekClient(**kwargs)
    elif provider == "openai":
        return OpenAIClient(**kwargs)
    elif provider == "mock":
        return MockLLMClient(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


# Quick test
if __name__ == "__main__":
    # Test mock client
    client = create_llm_client("mock", fail_first_n=0)

    system = "You are a ROSClaw-Native MCP Server generator."
    user = "Generate a test robot MCP server."

    code = client.generate(system, user)
    print(f"Generated {len(code)} characters of code")
