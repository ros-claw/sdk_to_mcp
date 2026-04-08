"""
Intel RealSense Point Cloud Export Example
Reference code for exporting point cloud data
"""
import pyrealsense2 as rs
import numpy as np
import open3d as o3d

# Create pipeline
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 1280, 720, rs.format.rgb8, 30)

# Start pipeline
pipeline.start(config)

# Create point cloud object
pc = rs.pointcloud()
points = rs.points()

# Wait for frames
frames = pipeline.wait_for_frames()
depth_frame = frames.get_depth_frame()
color_frame = frames.get_color_frame()

# Generate point cloud
pc.map_to(color_frame)
points = pc.calculate(depth_frame)

# Get vertices and texture coordinates
vertices = np.asanyarray(points.get_vertices())
texcoords = np.asanyarray(points.get_texture_coordinates())

# Convert to Open3D format
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(vertices.view(np.float32).reshape(-1, 3))

# Save to file
o3d.io.write_point_cloud("output.ply", pcd)

# Stop pipeline
pipeline.stop()
print("Point cloud saved to output.ply")
