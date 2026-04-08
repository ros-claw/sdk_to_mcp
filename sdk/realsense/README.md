# Intel RealSense SDK Reference

This directory contains reference SDK files for Intel RealSense depth cameras.

## SDK Information

- **Name**: librealsense / pyrealsense2
- **Version**: 2.51.0+
- **Manufacturer**: Intel
- **Models**: D435, D435i, D455, D415, D456, L515
- **Protocol**: USB3
- **Documentation**: https://dev.realsenseai.com/docs/docs-get-started

## Reference Files

### Official SDK Resources

- **GitHub**: https://github.com/IntelRealSense/librealsense
- **Python Docs**: https://pypi.org/project/pyrealsense2/
- **API Reference**: https://intelrealsense.github.io/librealsense/doxygen/annotated.html

### Local Reference

- `bridge_reference.py` - Python SDK usage patterns (from ros-claw/librealsense-mcp)
- `examples/` - Common usage examples
- `wrappers/` - ROS2 and other wrappers reference

## Camera Specifications

| Model | RGB Resolution | Depth Resolution | FOV | Range |
|-------|---------------|------------------|-----|-------|
| D435 | 1920x1080 | 1280x720 | 69°x42° | 0.3-10m |
| D435i | 1920x1080 | 1280x720 | 69°x42° | 0.3-10m |
| D455 | 1280x800 | 1280x720 | 87°x58° | 0.6-20m |
| L515 | 1920x1080 | 1024x768 | 70°x55° | 0.25-9m |

## Key SDK Components

### pyrealsense2 Python API

```python
import pyrealsense2 as rs

# Create pipeline
pipeline = rs.pipeline()
config = rs.config()

# Enable streams
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

# Start pipeline
pipeline.start(config)

# Get frames
frames = pipeline.wait_for_frames()
depth_frame = frames.get_depth_frame()
color_frame = frames.get_color_frame()

# Stop pipeline
pipeline.stop()
```

## Post-Processing Filters

1. **Decimation Filter** - Reduces depth scene complexity
2. **Spatial Filter** - Edge-preserving spatial smoothing
3. **Temporal Filter** - Reduces temporal noise
4. **Hole Filling Filter** - Fills holes in depth image

## Generated MCP Servers

Based on this SDK, the following MCP servers were generated:

1. **librealsense-mcp** - Direct SDK wrapper (pyrealsense2)
2. **realsense-ros-mcp** - ROS2 wrapper (realsense2_camera)

## Related Projects

- https://github.com/ros-claw/librealsense-mcp
- https://github.com/ros-claw/realsense-ros-mcp
