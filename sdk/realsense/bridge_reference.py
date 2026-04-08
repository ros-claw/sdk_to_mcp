"""
RealSenseBridge - pyrealsense2 封装层

线程安全的单例类，管理所有 RealSense 设备的 pipeline 生命周期、
帧捕获、滤波器、点云导出和设备控制。

基于 sdk_to_mcp 框架设计，包含完整的 SDK 元数据和安全约束。

用法:
    bridge = RealSenseBridge.instance()
    devices = bridge.list_devices()
    bridge.start_pipeline("231122070092")
    frame_info = bridge.capture_frames("231122070092")
    bridge.stop_pipeline("231122070092")

SDK Metadata:
    Name: librealsense (pyrealsense2)
    Version: 2.55.1+
    Source: https://github.com/IntelRealSense/librealsense
    Docs: https://intelrealsense.github.io/librealsense/doxygen/python_index.html
    License: Apache-2.0
"""

import os
import json
import time
import logging
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    rs = None  # 允许在无硬件环境下 import（测试用）

try:
    import cv2
except ImportError:
    cv2 = None

from safety_guard import SafetyGuard, SafetyError

# ── SDK Metadata ─────────────────────────────────────────────────────────────

@dataclass
class SDKMetadata:
    """
    SDK 元数据 - 基于 sdk_to_mcp 框架
    
    跟踪版本信息、源代码引用和依赖关系，
    确保 MCP server 与底层 SDK 保持同步。
    """
    name: str = "librealsense"
    version: str = "2.55.1+"
    protocol: str = "USB3.0/V4L2"
    source_url: str = "https://github.com/IntelRealSense/librealsense"
    doc_url: str = "https://intelrealsense.github.io/librealsense/doxygen/python_index.html"
    license: str = "Apache-2.0"
    hardware_models: List[str] = field(default_factory=lambda: [
        "D435", "D435i", "D455", "D415", "D405", "L515"
    ])
    dependencies: Dict[str, str] = field(default_factory=lambda: {
        "pyrealsense2": ">=2.55.1",
        "numpy": ">=1.20.0",
        "opencv-python": ">=4.5.0"
    })
    checksum: str = ""
    extracted_date: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = "Intel RealSense SDK 2.0 Python bindings"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def get_instance(cls) -> "SDKMetadata":
        """获取 SDK 元数据实例"""
        return cls()


logger = logging.getLogger("realsense.bridge")

# 默认帧输出目录
DEFAULT_OUTPUT_DIR = "/tmp/realsense"


def _ensure_dir(path: str) -> None:
    """确保目标文件的父目录存在。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _stream_type_from_str(name: str) -> "rs.stream":
    """将字符串流类型名转为 rs.stream 枚举。"""
    mapping = {
        "depth": rs.stream.depth,
        "color": rs.stream.color,
        "infrared": rs.stream.infrared,
        "gyro": rs.stream.gyro,
        "accel": rs.stream.accel,
    }
    key = name.lower().strip()
    if key not in mapping:
        raise ValueError(f"未知的流类型: {name}，可选: {list(mapping.keys())}")
    return mapping[key]


class PipelineContext:
    """单个设备的 pipeline 运行上下文。"""

    def __init__(
        self,
        serial: str,
        pipeline: "rs.pipeline",
        profile: "rs.pipeline_profile",
        config_params: Dict[str, Any],
    ):
        self.serial = serial
        self.pipeline = pipeline
        self.profile = profile
        self.config_params = config_params  # 启动参数，用于重连
        self.align: Optional["rs.align"] = None
        self.last_frames: Optional["rs.composite_frame"] = None
        self.last_timestamp: float = 0.0
        self.filters: Dict[str, Any] = {}  # 激活的滤波器
        self.started_at: float = time.time()

    @property
    def device(self) -> "rs.device":
        return self.profile.get_device()

    @property
    def depth_scale(self) -> float:
        try:
            return self.device.first_depth_sensor().get_depth_scale()
        except Exception:
            return 0.001


class RealSenseBridge:
    """
    RealSense 设备管理器 — 线程安全单例。

    管理多台 RealSense 相机的 pipeline 生命周期、帧捕获、
    点云导出、滤波器配置和传感器控制。
    """

    _instance: Optional["RealSenseBridge"] = None
    _init_lock = threading.Lock()

    # ── 单例 ──────────────────────────────────────────────────────────────

    @classmethod
    def instance(cls) -> "RealSenseBridge":
        """获取或创建单例实例。"""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if rs is None:
            raise RuntimeError("pyrealsense2 未安装或无法导入")
        self._lock = threading.Lock()
        self._pipelines: Dict[str, PipelineContext] = {}
        self._ctx = rs.context()
        logger.info("RealSenseBridge 已初始化")

    def __del__(self) -> None:
        """析构时停止所有 pipeline。"""
        self.stop_all()

    # ── 设备发现 ──────────────────────────────────────────────────────────

    def list_devices(self) -> List[Dict[str, str]]:
        """
        列出所有已连接的 RealSense 设备。

        Returns:
            设备信息列表，每项包含 serial / name / firmware_version / product_line
        """
        devices: List[Dict[str, str]] = []
        for dev in self._ctx.query_devices():
            name = dev.get_info(rs.camera_info.name)
            if name.lower() == "platform camera":
                continue
            devices.append({
                "serial": dev.get_info(rs.camera_info.serial_number),
                "name": name,
                "firmware_version": dev.get_info(rs.camera_info.firmware_version),
                "product_line": dev.get_info(rs.camera_info.product_line),
            })
        logger.info(f"发现 {len(devices)} 台 RealSense 设备")
        return devices

    def get_device_info(self, serial: str) -> Dict[str, Any]:
        """
        获取指定设备的详细信息。

        Args:
            serial: 设备序列号

        Returns:
            设备详细信息字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        dev = self._find_device(serial)
        info: Dict[str, Any] = {}
        for attr in dir(rs.camera_info):
            if attr.startswith("_"):
                continue
            ci = getattr(rs.camera_info, attr)
            try:
                if dev.supports(ci):
                    info[attr] = dev.get_info(ci)
            except Exception:
                pass
        # 传感器信息
        sensors_info = []
        for sensor in dev.sensors:
            sensors_info.append({
                "name": sensor.get_info(rs.camera_info.name),
                "profiles_count": len(sensor.get_stream_profiles()),
            })
        info["sensors"] = sensors_info
        info["is_pipeline_active"] = serial in self._pipelines
        return info

    def hardware_reset(self, serial: str) -> None:
        """
        硬件重置指定设备。

        Args:
            serial: 设备序列号
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        with self._lock:
            # 先停止 pipeline（如果存在）
            if serial in self._pipelines:
                self._stop_pipeline_unsafe(serial)
        dev = self._find_device(serial)
        dev.hardware_reset()
        logger.info(f"设备 {serial} 已硬件重置")

    # ── Pipeline 生命周期 ────────────────────────────────────────────────

    def start_pipeline(
        self,
        serial: str,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        enable_color: bool = True,
        enable_depth: bool = True,
        enable_infrared: bool = False,
        enable_imu: bool = False,
    ) -> Dict[str, Any]:
        """
        启动指定设备的流。

        Args:
            serial: 设备序列号
            width: 图像宽度
            height: 图像高度
            fps: 帧率
            enable_color: 是否启用彩色流
            enable_depth: 是否启用深度流
            enable_infrared: 是否启用红外流
            enable_imu: 是否启用 IMU 流

        Returns:
            启动结果信息
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_resolution(width, height))
        SafetyGuard.check(*SafetyGuard.validate_fps(fps))

        with self._lock:
            if serial in self._pipelines:
                raise RuntimeError(f"设备 {serial} 的 pipeline 已在运行中，请先停止")

            config_params = {
                "serial": serial, "width": width, "height": height, "fps": fps,
                "enable_color": enable_color, "enable_depth": enable_depth,
                "enable_infrared": enable_infrared, "enable_imu": enable_imu,
            }

            pipeline = rs.pipeline(self._ctx)
            config = rs.config()
            config.enable_device(serial)

            streams_enabled: List[str] = []
            if enable_depth:
                config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
                streams_enabled.append("depth")
            if enable_color:
                config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
                streams_enabled.append("color")
            if enable_infrared:
                config.enable_stream(rs.stream.infrared, 1, width, height, rs.format.y8, fps)
                streams_enabled.append("infrared_1")
            if enable_imu:
                config.enable_stream(rs.stream.accel)
                config.enable_stream(rs.stream.gyro)
                streams_enabled.append("accel")
                streams_enabled.append("gyro")

            try:
                profile = pipeline.start(config)
            except Exception as e:
                raise RuntimeError(f"启动 pipeline 失败 ({serial}): {e}")

            ctx = PipelineContext(serial, pipeline, profile, config_params)
            self._pipelines[serial] = ctx

            logger.info(f"Pipeline 已启动: {serial} ({width}x{height}@{fps}fps, streams={streams_enabled})")
            return {
                "serial": serial,
                "streams": streams_enabled,
                "resolution": f"{width}x{height}",
                "fps": fps,
                "depth_scale": ctx.depth_scale,
            }

    def stop_pipeline(self, serial: str) -> None:
        """
        停止指定设备的流。

        Args:
            serial: 设备序列号
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        with self._lock:
            self._stop_pipeline_unsafe(serial)

    def _stop_pipeline_unsafe(self, serial: str) -> None:
        """内部停止 pipeline（调用者需持有锁）。"""
        ctx = self._pipelines.pop(serial, None)
        if ctx is None:
            raise RuntimeError(f"设备 {serial} 无活动的 pipeline")
        try:
            ctx.pipeline.stop()
        except Exception as e:
            logger.warning(f"停止 pipeline 异常 ({serial}): {e}")
        logger.info(f"Pipeline 已停止: {serial}")

    def stop_all(self) -> None:
        """停止所有 pipeline。"""
        with self._lock:
            for serial in list(self._pipelines.keys()):
                try:
                    self._stop_pipeline_unsafe(serial)
                except Exception as e:
                    logger.warning(f"停止 {serial} 时异常: {e}")

    def get_pipeline_status(self) -> List[Dict[str, Any]]:
        """
        获取所有活动 pipeline 的状态。

        Returns:
            pipeline 状态列表
        """
        with self._lock:
            result: List[Dict[str, Any]] = []
            for serial, ctx in self._pipelines.items():
                result.append({
                    "serial": serial,
                    "config": ctx.config_params,
                    "depth_scale": ctx.depth_scale,
                    "uptime_seconds": round(time.time() - ctx.started_at, 1),
                    "filters": list(ctx.filters.keys()),
                    "has_cached_frame": ctx.last_frames is not None,
                })
            return result

    # ── 帧捕获 ────────────────────────────────────────────────────────────

    def _get_ctx(self, serial: str) -> PipelineContext:
        """获取 pipeline 上下文（需在锁内调用或独立使用）。"""
        ctx = self._pipelines.get(serial)
        if ctx is None:
            raise RuntimeError(f"设备 {serial} 无活动的 pipeline，请先调用 start_pipeline")
        return ctx

    def _wait_frames(self, serial: str, timeout_ms: int = 5000) -> "rs.composite_frame":
        """
        等待新帧，带自动重连逻辑。

        Args:
            serial: 设备序列号
            timeout_ms: 超时毫秒数

        Returns:
            帧集合
        """
        ctx = self._get_ctx(serial)
        try:
            frames = ctx.pipeline.wait_for_frames(timeout_ms)
            ctx.last_frames = frames
            ctx.last_timestamp = time.time()
            return frames
        except Exception as e:
            logger.warning(f"wait_for_frames 失败 ({serial}): {e}，尝试重连...")
            # 尝试自动重连
            try:
                with self._lock:
                    self._stop_pipeline_unsafe(serial)
            except Exception:
                pass
            params = ctx.config_params
            self.start_pipeline(**params)
            # 再次等待
            new_ctx = self._get_ctx(serial)
            frames = new_ctx.pipeline.wait_for_frames(timeout_ms)
            new_ctx.last_frames = frames
            new_ctx.last_timestamp = time.time()
            return frames

    def capture_frames(self, serial: str, align_depth: bool = True) -> Dict[str, Any]:
        """
        捕获一组帧，返回元数据。

        Args:
            serial: 设备序列号
            align_depth: 是否对齐深度到彩色

        Returns:
            帧元数据字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        frames = self._wait_frames(serial)
        ctx = self._get_ctx(serial)

        result: Dict[str, Any] = {"serial": serial, "timestamp": time.time()}

        if align_depth:
            align = rs.align(rs.stream.color)
            frames = align.process(frames)

        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        if depth_frame:
            dp = depth_frame.get_profile().as_video_stream_profile()
            result["depth"] = {
                "width": dp.width(),
                "height": dp.height(),
                "fps": dp.fps(),
                "frame_number": depth_frame.get_frame_number(),
                "timestamp_ms": depth_frame.get_timestamp(),
            }

        if color_frame:
            cp = color_frame.get_profile().as_video_stream_profile()
            result["color"] = {
                "width": cp.width(),
                "height": cp.height(),
                "fps": cp.fps(),
                "frame_number": color_frame.get_frame_number(),
                "timestamp_ms": color_frame.get_timestamp(),
            }

        result["depth_scale"] = ctx.depth_scale
        result["aligned"] = align_depth
        return result

    def capture_color_image(self, serial: str, save_path: str) -> Dict[str, Any]:
        """
        捕获彩色图像并保存。

        Args:
            serial: 设备序列号
            save_path: 保存路径 (.png / .jpg)

        Returns:
            包含保存路径和图像信息的字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_file_path(save_path))

        frames = self._wait_frames(serial)
        color_frame = frames.get_color_frame()
        if not color_frame:
            raise RuntimeError(f"设备 {serial} 未返回彩色帧 (是否启用了 color 流?)")

        color_data = np.asanyarray(color_frame.get_data())
        _ensure_dir(save_path)
        if cv2 is not None:
            cv2.imwrite(save_path, color_data)
        else:
            # 后备: 使用 numpy 保存 raw
            np.save(save_path + ".npy", color_data)
            save_path = save_path + ".npy"

        cp = color_frame.get_profile().as_video_stream_profile()
        logger.info(f"彩色图已保存: {save_path}")
        return {
            "path": save_path,
            "width": cp.width(),
            "height": cp.height(),
            "channels": 3,
            "frame_number": color_frame.get_frame_number(),
        }

    def capture_depth_image(
        self, serial: str, save_path: str, colorize: bool = True
    ) -> Dict[str, Any]:
        """
        捕获深度图像并保存。

        Args:
            serial: 设备序列号
            save_path: 保存路径
            colorize: 是否应用伪彩色

        Returns:
            包含保存路径和图像信息的字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_file_path(save_path))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧 (是否启用了 depth 流?)")

        # 应用滤波器
        depth_frame = self._apply_filters(serial, depth_frame)

        _ensure_dir(save_path)

        if colorize:
            colorizer = rs.colorizer()
            colorized = colorizer.colorize(depth_frame)
            depth_data = np.asanyarray(colorized.get_data())
        else:
            depth_data = np.asanyarray(depth_frame.get_data())

        if cv2 is not None:
            if not colorize:
                # 16-bit 深度图需要特殊处理
                cv2.imwrite(save_path, depth_data)
            else:
                cv2.imwrite(save_path, depth_data)
        else:
            np.save(save_path + ".npy", depth_data)
            save_path = save_path + ".npy"

        dp = depth_frame.get_profile().as_video_stream_profile()
        logger.info(f"深度图已保存: {save_path}")
        return {
            "path": save_path,
            "width": dp.width(),
            "height": dp.height(),
            "colorized": colorize,
            "frame_number": depth_frame.get_frame_number(),
        }

    def capture_aligned_rgbd(
        self, serial: str, color_path: str, depth_path: str
    ) -> Dict[str, Any]:
        """
        捕获对齐的 RGBD 图像并分别保存。

        Args:
            serial: 设备序列号
            color_path: 彩色图保存路径
            depth_path: 深度图保存路径

        Returns:
            包含两张图路径和信息的字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_file_path(color_path))
        SafetyGuard.check(*SafetyGuard.validate_file_path(depth_path))

        frames = self._wait_frames(serial)

        # 对齐
        align = rs.align(rs.stream.color)
        aligned = align.process(frames)

        color_frame = aligned.get_color_frame()
        depth_frame = aligned.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError(f"设备 {serial} 对齐帧获取失败")

        # 应用滤波器
        depth_frame = self._apply_filters(serial, depth_frame)

        color_data = np.asanyarray(color_frame.get_data())
        depth_data = np.asanyarray(depth_frame.get_data())

        _ensure_dir(color_path)
        _ensure_dir(depth_path)

        if cv2 is not None:
            cv2.imwrite(color_path, color_data)
            # 深度保存为 16-bit PNG（无损）
            cv2.imwrite(depth_path, depth_data)
        else:
            np.save(color_path + ".npy", color_data)
            np.save(depth_path + ".npy", depth_data)
            color_path += ".npy"
            depth_path += ".npy"

        cp = color_frame.get_profile().as_video_stream_profile()
        dp = depth_frame.get_profile().as_video_stream_profile()
        ctx = self._get_ctx(serial)

        logger.info(f"对齐 RGBD 已保存: color={color_path}, depth={depth_path}")
        return {
            "color_path": color_path,
            "depth_path": depth_path,
            "width": cp.width(),
            "height": cp.height(),
            "depth_scale": ctx.depth_scale,
            "aligned": True,
        }

    # ── 深度测量 ──────────────────────────────────────────────────────────

    def get_distance(self, serial: str, x: int, y: int) -> Dict[str, Any]:
        """
        获取指定像素的深度值。

        Args:
            serial: 设备序列号
            x: 像素 x 坐标
            y: 像素 y 坐标

        Returns:
            深度值信息 (米)
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧")

        dp = depth_frame.get_profile().as_video_stream_profile()
        SafetyGuard.check(*SafetyGuard.validate_pixel(x, y, dp.width(), dp.height()))

        distance = depth_frame.get_distance(x, y)
        return {
            "serial": serial,
            "x": x,
            "y": y,
            "distance_meters": round(distance, 4),
            "frame_width": dp.width(),
            "frame_height": dp.height(),
        }

    def get_depth_stats(
        self,
        serial: str,
        roi_x: Optional[int] = None,
        roi_y: Optional[int] = None,
        roi_w: Optional[int] = None,
        roi_h: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取深度统计信息。

        Args:
            serial: 设备序列号
            roi_x: ROI 起始 x（可选）
            roi_y: ROI 起始 y（可选）
            roi_w: ROI 宽度（可选）
            roi_h: ROI 高度（可选）

        Returns:
            深度统计信息 (min/max/mean/std，单位: 米)
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧")

        # 应用滤波器
        depth_frame = self._apply_filters(serial, depth_frame)

        depth_data = np.asanyarray(depth_frame.get_data()).astype(np.float64)
        dp = depth_frame.get_profile().as_video_stream_profile()
        ctx = self._get_ctx(serial)
        scale = ctx.depth_scale

        h, w = depth_data.shape

        # 提取 ROI
        if roi_x is not None and roi_y is not None and roi_w is not None and roi_h is not None:
            SafetyGuard.check(*SafetyGuard.validate_roi(roi_x, roi_y, roi_w, roi_h, w, h))
            roi = depth_data[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
        else:
            roi = depth_data
            roi_x, roi_y, roi_w, roi_h = 0, 0, w, h

        # 转换为米 (排除零值/无效值)
        roi_meters = roi * scale
        valid_mask = roi_meters > 0
        valid_pixels = roi_meters[valid_mask]

        if valid_pixels.size == 0:
            return {
                "serial": serial,
                "roi": {"x": roi_x, "y": roi_y, "w": roi_w, "h": roi_h},
                "valid_pixels": 0,
                "total_pixels": int(roi.size),
                "min_m": None,
                "max_m": None,
                "mean_m": None,
                "std_m": None,
            }

        return {
            "serial": serial,
            "roi": {"x": roi_x, "y": roi_y, "w": roi_w, "h": roi_h},
            "valid_pixels": int(valid_pixels.size),
            "total_pixels": int(roi.size),
            "min_m": round(float(valid_pixels.min()), 4),
            "max_m": round(float(valid_pixels.max()), 4),
            "mean_m": round(float(valid_pixels.mean()), 4),
            "std_m": round(float(valid_pixels.std()), 4),
        }

    # ── 点云 ──────────────────────────────────────────────────────────────

    def capture_pointcloud(
        self, serial: str, save_path: str, with_color: bool = True
    ) -> Dict[str, Any]:
        """
        捕获点云并导出为 PLY 文件。

        Args:
            serial: 设备序列号
            save_path: PLY 文件保存路径
            with_color: 是否包含颜色纹理

        Returns:
            点云导出信息
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_file_path(save_path))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧")

        # 应用滤波器
        depth_frame = self._apply_filters(serial, depth_frame)

        _ensure_dir(save_path)

        pc = rs.pointcloud()
        if with_color and color_frame:
            pc.map_to(color_frame)
        points = pc.calculate(depth_frame)

        # 使用 save_to_ply
        ply = rs.save_to_ply(save_path)
        ply.set_option(rs.save_to_ply.option_ply_binary, True)
        ply.set_option(rs.save_to_ply.option_ply_normals, False)

        if with_color and color_frame:
            # 需要传入包含深度和颜色的帧集合
            ply.process(frames)
        else:
            colorizer = rs.colorizer()
            colorized = colorizer.process(frames)
            ply.process(colorized)

        vertex_count = points.size()
        logger.info(f"点云已保存: {save_path} ({vertex_count} 个顶点)")
        return {
            "path": save_path,
            "vertex_count": vertex_count,
            "with_color": with_color,
        }

    def get_pointcloud_data(
        self, serial: str, downsample: int = 1
    ) -> Dict[str, Any]:
        """
        获取点云顶点数据摘要。

        Args:
            serial: 设备序列号
            downsample: 降采样步长

        Returns:
            点云统计摘要
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_downsample(downsample))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧")

        depth_frame = self._apply_filters(serial, depth_frame)

        pc = rs.pointcloud()
        points = pc.calculate(depth_frame)
        vertices = np.asanyarray(points.get_vertices()).view(np.float32).reshape(-1, 3)

        # 降采样
        if downsample > 1:
            vertices = vertices[::downsample]

        # 过滤无效点 (全零)
        valid_mask = np.any(vertices != 0, axis=1)
        valid = vertices[valid_mask]

        result: Dict[str, Any] = {
            "serial": serial,
            "total_points": int(vertices.shape[0]),
            "valid_points": int(valid.shape[0]),
            "downsample": downsample,
        }

        if valid.shape[0] > 0:
            result["bounds"] = {
                "x_min": round(float(valid[:, 0].min()), 4),
                "x_max": round(float(valid[:, 0].max()), 4),
                "y_min": round(float(valid[:, 1].min()), 4),
                "y_max": round(float(valid[:, 1].max()), 4),
                "z_min": round(float(valid[:, 2].min()), 4),
                "z_max": round(float(valid[:, 2].max()), 4),
            }
            result["centroid"] = {
                "x": round(float(valid[:, 0].mean()), 4),
                "y": round(float(valid[:, 1].mean()), 4),
                "z": round(float(valid[:, 2].mean()), 4),
            }
        return result

    # ── 滤波器 ────────────────────────────────────────────────────────────

    def apply_depth_filters(
        self,
        serial: str,
        decimation: bool = False,
        spatial: bool = True,
        temporal: bool = True,
        hole_filling: bool = False,
        threshold_min: float = 0.1,
        threshold_max: float = 10.0,
    ) -> Dict[str, Any]:
        """
        配置深度滤波器。配置后的滤波器会应用于该设备后续所有深度帧。

        Args:
            serial: 设备序列号
            decimation: 是否启用抽取滤波器
            spatial: 是否启用空间滤波器
            temporal: 是否启用时间滤波器
            hole_filling: 是否启用孔洞填充
            threshold_min: 距离阈值下限 (米)
            threshold_max: 距离阈值上限 (米)

        Returns:
            已启用的滤波器列表
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        SafetyGuard.check(*SafetyGuard.validate_distance_threshold(threshold_min, threshold_max))

        ctx = self._get_ctx(serial)
        filters: Dict[str, Any] = {}

        # 阈值滤波器 (始终启用)
        thresh = rs.threshold_filter()
        thresh.set_option(rs.option.min_distance, threshold_min)
        thresh.set_option(rs.option.max_distance, threshold_max)
        filters["threshold"] = thresh

        if decimation:
            filters["decimation"] = rs.decimation_filter()
        if spatial:
            filters["spatial"] = rs.spatial_filter()
        if temporal:
            filters["temporal"] = rs.temporal_filter()
        if hole_filling:
            filters["hole_filling"] = rs.hole_filling_filter()

        ctx.filters = filters
        enabled_list = list(filters.keys())
        logger.info(f"设备 {serial} 滤波器已配置: {enabled_list}")
        return {
            "serial": serial,
            "filters_enabled": enabled_list,
            "threshold_min_m": threshold_min,
            "threshold_max_m": threshold_max,
        }

    def _apply_filters(self, serial: str, depth_frame: "rs.depth_frame") -> "rs.depth_frame":
        """对深度帧应用已配置的滤波器链。"""
        ctx = self._pipelines.get(serial)
        if ctx is None or not ctx.filters:
            return depth_frame

        frame = depth_frame
        # 按固定顺序应用
        order = ["threshold", "decimation", "spatial", "temporal", "hole_filling"]
        for name in order:
            f = ctx.filters.get(name)
            if f is not None:
                frame = f.process(frame)
        return frame.as_depth_frame()

    # ── 标定信息 ──────────────────────────────────────────────────────────

    def get_intrinsics(self, serial: str, stream_type: str = "depth") -> Dict[str, Any]:
        """
        获取相机内参。

        Args:
            serial: 设备序列号
            stream_type: 流类型 ("depth" / "color" / "infrared")

        Returns:
            内参字典 (width, height, ppx, ppy, fx, fy, model, coeffs)
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        frames = self._wait_frames(serial)
        st = _stream_type_from_str(stream_type)

        # 在帧中查找对应流
        for i in range(frames.size()):
            frame = frames[i]
            profile = frame.get_profile()
            if profile.stream_type() == st:
                vsp = profile.as_video_stream_profile()
                intr = vsp.get_intrinsics()
                return {
                    "stream": stream_type,
                    "width": intr.width,
                    "height": intr.height,
                    "ppx": round(intr.ppx, 4),
                    "ppy": round(intr.ppy, 4),
                    "fx": round(intr.fx, 4),
                    "fy": round(intr.fy, 4),
                    "model": str(intr.model),
                    "coeffs": [round(c, 6) for c in intr.coeffs],
                }

        raise RuntimeError(f"帧集中未找到 {stream_type} 流")

    def get_extrinsics(
        self, serial: str, from_stream: str = "depth", to_stream: str = "color"
    ) -> Dict[str, Any]:
        """
        获取两个流之间的外参。

        Args:
            serial: 设备序列号
            from_stream: 源流类型
            to_stream: 目标流类型

        Returns:
            外参字典 (rotation 3x3, translation 3)
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        frames = self._wait_frames(serial)
        from_st = _stream_type_from_str(from_stream)
        to_st = _stream_type_from_str(to_stream)

        from_profile = None
        to_profile = None

        for i in range(frames.size()):
            frame = frames[i]
            p = frame.get_profile()
            if p.stream_type() == from_st and from_profile is None:
                from_profile = p
            if p.stream_type() == to_st and to_profile is None:
                to_profile = p

        if from_profile is None:
            raise RuntimeError(f"帧集中未找到 {from_stream} 流")
        if to_profile is None:
            raise RuntimeError(f"帧集中未找到 {to_stream} 流")

        ext = from_profile.get_extrinsics_to(to_profile)
        return {
            "from": from_stream,
            "to": to_stream,
            "rotation": [round(r, 6) for r in ext.rotation],
            "translation": [round(t, 6) for t in ext.translation],
        }

    def deproject_pixel(self, serial: str, x: int, y: int) -> Dict[str, Any]:
        """
        将像素坐标 + 深度反投影为 3D 坐标。

        Args:
            serial: 设备序列号
            x: 像素 x
            y: 像素 y

        Returns:
            3D 点坐标 (米)
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        frames = self._wait_frames(serial)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError(f"设备 {serial} 未返回深度帧")

        dp = depth_frame.get_profile().as_video_stream_profile()
        SafetyGuard.check(*SafetyGuard.validate_pixel(x, y, dp.width(), dp.height()))

        depth = depth_frame.get_distance(x, y)
        intrinsics = dp.get_intrinsics()
        point_3d = rs.rs2_deproject_pixel_to_point(intrinsics, [x, y], depth)

        return {
            "serial": serial,
            "pixel": {"x": x, "y": y},
            "depth_m": round(depth, 4),
            "point_3d": {
                "x": round(point_3d[0], 4),
                "y": round(point_3d[1], 4),
                "z": round(point_3d[2], 4),
            },
        }

    # ── 设备控制 ──────────────────────────────────────────────────────────

    def _get_sensor(self, serial: str, sensor_name: str) -> "rs.sensor":
        """按名称获取传感器。"""
        ctx = self._get_ctx(serial)
        name_lower = sensor_name.lower().strip()
        for sensor in ctx.device.sensors:
            sn = sensor.get_info(rs.camera_info.name).lower()
            if name_lower in sn:
                return sensor
        # fallback: depth = first_depth_sensor
        if "depth" in name_lower:
            return ctx.device.first_depth_sensor()
        raise RuntimeError(
            f"设备 {serial} 未找到名为 '{sensor_name}' 的传感器。"
            f"可用: {[s.get_info(rs.camera_info.name) for s in ctx.device.sensors]}"
        )

    def get_sensor_options(
        self, serial: str, sensor_name: str = "depth"
    ) -> Dict[str, Any]:
        """
        列出传感器可用选项及当前值。

        Args:
            serial: 设备序列号
            sensor_name: 传感器名称 ("depth" / "color" / "RGB Camera" 等)

        Returns:
            选项字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        sensor = self._get_sensor(serial, sensor_name)
        options: Dict[str, Any] = {}
        for opt in sensor.get_supported_options():
            try:
                rng = sensor.get_option_range(opt)
                options[opt.name] = {
                    "value": sensor.get_option(opt),
                    "min": rng.min,
                    "max": rng.max,
                    "step": rng.step,
                    "default": rng.default,
                    "description": sensor.get_option_description(opt),
                }
            except Exception:
                pass
        return {
            "serial": serial,
            "sensor": sensor_name,
            "options": options,
        }

    def set_sensor_option(
        self, serial: str, sensor_name: str, option_name: str, value: float
    ) -> Dict[str, Any]:
        """
        设置传感器选项值。

        Args:
            serial: 设备序列号
            sensor_name: 传感器名称
            option_name: 选项名称 (如 "exposure", "gain" 等)
            value: 值

        Returns:
            设置结果
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        sensor = self._get_sensor(serial, sensor_name)

        # 查找选项
        target_opt = None
        for opt in sensor.get_supported_options():
            if opt.name.lower() == option_name.lower().strip():
                target_opt = opt
                break
        if target_opt is None:
            raise RuntimeError(
                f"传感器 '{sensor_name}' 不支持选项 '{option_name}'。"
            )

        rng = sensor.get_option_range(target_opt)
        if value < rng.min or value > rng.max:
            raise SafetyError(
                f"选项 '{option_name}' 值 {value} 超出范围 [{rng.min}, {rng.max}]"
            )

        sensor.set_option(target_opt, value)
        logger.info(f"设备 {serial} 传感器 {sensor_name} 选项 {option_name} = {value}")
        return {
            "serial": serial,
            "sensor": sensor_name,
            "option": option_name,
            "value": value,
            "range": {"min": rng.min, "max": rng.max, "step": rng.step},
        }

    def set_emitter(self, serial: str, enabled: bool) -> Dict[str, Any]:
        """
        控制 IR 发射器。

        Args:
            serial: 设备序列号
            enabled: 是否启用

        Returns:
            操作结果
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        ctx = self._get_ctx(serial)
        sensor = ctx.device.first_depth_sensor()

        if not sensor.supports(rs.option.emitter_enabled):
            raise RuntimeError(f"设备 {serial} 不支持 IR 发射器控制")

        sensor.set_option(rs.option.emitter_enabled, 1.0 if enabled else 0.0)
        logger.info(f"设备 {serial} IR 发射器: {'启用' if enabled else '禁用'}")
        return {
            "serial": serial,
            "emitter_enabled": enabled,
        }

    def set_exposure(
        self, serial: str, auto: bool = True, value: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置曝光。

        Args:
            serial: 设备序列号
            auto: 是否自动曝光
            value: 手动曝光值（auto=False 时生效）

        Returns:
            操作结果
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        ctx = self._get_ctx(serial)
        sensor = ctx.device.first_depth_sensor()

        if sensor.supports(rs.option.enable_auto_exposure):
            sensor.set_option(rs.option.enable_auto_exposure, 1.0 if auto else 0.0)

        if not auto and value is not None:
            if sensor.supports(rs.option.exposure):
                rng = sensor.get_option_range(rs.option.exposure)
                clamped = max(rng.min, min(rng.max, float(value)))
                sensor.set_option(rs.option.exposure, clamped)

        current_exp = None
        if sensor.supports(rs.option.exposure):
            current_exp = sensor.get_option(rs.option.exposure)

        logger.info(f"设备 {serial} 曝光: auto={auto}, value={value}")
        return {
            "serial": serial,
            "auto_exposure": auto,
            "exposure_value": current_exp,
        }

    # ── 高级模式 ──────────────────────────────────────────────────────────

    def get_advanced_mode_json(self, serial: str) -> Dict[str, Any]:
        """
        导出 D400 高级模式 JSON。

        Args:
            serial: 设备序列号

        Returns:
            包含 JSON 字符串的字典
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))
        dev = self._find_device(serial)
        try:
            advnc = rs.rs400_advanced_mode(dev)
            if not advnc.is_enabled():
                advnc.toggle_advanced_mode(True)
                # 等待设备重启
                import time
                time.sleep(2)
                dev = self._find_device(serial)
                advnc = rs.rs400_advanced_mode(dev)
            json_str = advnc.serialize_json()
            return {
                "serial": serial,
                "advanced_mode_enabled": True,
                "json": json_str,
            }
        except Exception as e:
            raise RuntimeError(f"获取高级模式失败 ({serial}): {e}")

    def load_advanced_mode_json(self, serial: str, json_path: str) -> Dict[str, Any]:
        """
        加载高级模式 JSON 配置。

        Args:
            serial: 设备序列号
            json_path: JSON 文件路径

        Returns:
            加载结果
        """
        SafetyGuard.check(*SafetyGuard.validate_serial(serial))

        if not os.path.isfile(json_path):
            raise FileNotFoundError(f"JSON 文件不存在: {json_path}")

        with open(json_path, "r") as f:
            json_text = f.read().strip()

        dev = self._find_device(serial)
        try:
            advnc = rs.rs400_advanced_mode(dev)
            if not advnc.is_enabled():
                advnc.toggle_advanced_mode(True)
                time.sleep(2)
                dev = self._find_device(serial)
                advnc = rs.rs400_advanced_mode(dev)
            advnc.load_json(json_text)
            logger.info(f"设备 {serial} 已加载高级模式配置: {json_path}")
            return {
                "serial": serial,
                "json_path": json_path,
                "loaded": True,
            }
        except Exception as e:
            raise RuntimeError(f"加载高级模式失败 ({serial}): {e}")

    # ── 多相机 ────────────────────────────────────────────────────────────

    def start_multi_pipeline(
        self, configs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量启动多个相机。

        Args:
            configs: 配置列表，每项包含 serial 及可选的 width/height/fps 等

        Returns:
            各相机启动结果列表
        """
        results: List[Dict[str, Any]] = []
        for cfg in configs:
            serial = cfg.get("serial")
            if not serial:
                results.append({"error": "缺少 serial 字段", "config": cfg})
                continue
            try:
                r = self.start_pipeline(
                    serial=serial,
                    width=cfg.get("width", 640),
                    height=cfg.get("height", 480),
                    fps=cfg.get("fps", 30),
                    enable_color=cfg.get("enable_color", True),
                    enable_depth=cfg.get("enable_depth", True),
                    enable_infrared=cfg.get("enable_infrared", False),
                    enable_imu=cfg.get("enable_imu", False),
                )
                results.append(r)
            except Exception as e:
                results.append({"serial": serial, "error": str(e)})
        return results

    def capture_multi_frames(
        self, serials: List[str], align_depth: bool = True
    ) -> List[Dict[str, Any]]:
        """
        同时从多个相机捕获帧。

        Args:
            serials: 设备序列号列表
            align_depth: 是否对齐深度到彩色

        Returns:
            各相机帧元数据列表
        """
        results: List[Dict[str, Any]] = []
        for serial in serials:
            try:
                r = self.capture_frames(serial, align_depth=align_depth)
                results.append(r)
            except Exception as e:
                results.append({"serial": serial, "error": str(e)})
        return results

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _find_device(self, serial: str) -> "rs.device":
        """按序列号查找设备。"""
        for dev in self._ctx.query_devices():
            if dev.get_info(rs.camera_info.serial_number) == serial:
                return dev
        raise RuntimeError(f"未找到序列号为 {serial} 的 RealSense 设备")
