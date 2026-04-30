"""Tests for rosclaw_unitree_go2_mcp server."""

import pytest
from rosclaw_unitree_go2_mcp import __version__, mcp, ROSClawUnitreeGo2Client


def test_version():
    """Test version is defined."""
    assert __version__ == "1.0.0"


def test_imports():
    """Test main imports work."""
    assert mcp is not None
    assert ROSClawUnitreeGo2Client is not None


@pytest.mark.asyncio
async def test_client_initialization():
    """Test client can be initialized."""
    # Note: This requires ROS 2 environment
    # client = ROSClawUnitreeGo2Client()
    # await client.start()
    # await client.stop()
    pass
