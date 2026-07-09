"""터틀봇3 대시보드 메인 윈도우."""
import math
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QMainWindow, QTabWidget, QLabel, QWidget, QVBoxLayout

from dashboard import theme
from dashboard.ros_bridge import RosBridge, RosThread
from dashboard.widgets.status_panel import StatusPanel
from dashboard.widgets.control_panel import ControlPanel
from dashboard.widgets.log_panel import LogPanel
from dashboard.widgets.nav_panel import NavPanel
from dashboard.widgets.map_panel import MapPanel
from dashboard.widgets.ssh_panel import SshPanel

LOW_BATTERY_THRESHOLD = 0.2
OBSTACLE_WARN_DISTANCE_M = 0.3

LINK_NAME_KO = {
    'odom': 'Odometry',
    'battery_state': '배터리',
    'scan': 'LiDAR',
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        model = os.environ.get("TURTLEBOT3_MODEL", "알 수 없음")
        self.setWindowTitle(f"TurtleBot3 Dashboard ({model})")
        self.resize(1100, 780)
        self.setMinimumSize(760, 560)

        self.bridge = RosBridge()
        self.ros_thread = RosThread(self.bridge)

        self.status_panel = StatusPanel()
        self.control_panel = ControlPanel()
        self.map_panel = MapPanel()
        self.nav_panel = NavPanel()
        self.log_panel = LogPanel()
        self.ssh_panel = SshPanel()

        tabs = QTabWidget()
        tabs.addTab(self.control_panel, "동작 컨트롤")
        tabs.addTab(self.map_panel, "맵 / 웨이포인트 생성")
        tabs.addTab(self.nav_panel, "웨이포인트 주행")
        tabs.addTab(self.log_panel, "이벤트 로그")

        self.header_label = QLabel("ROS2 노드 초기화 중...")
        self.header_label.setStyleSheet(
            f"padding: 6px 2px; font-weight: 600; color: {theme.TEXT_SECONDARY};"
        )

        central = QWidget()
        central.setObjectName("Central")
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self.ssh_panel)
        layout.addWidget(self.header_label)
        layout.addWidget(self.status_panel)
        layout.addWidget(tabs, 1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._battery_low_notified = False
        self._obstacle_notified = False
        self._link_status = {key: 'down' for key in LINK_NAME_KO}
        self.ssh_panel.set_robot_status(self._robot_ready_state())

        self._connect_signals()

        # 시그널 연결이 끝난 뒤에 불러와야 초기 자동 로드 결과가 지도 동기화로
        # 이어진다(연결 전에 불러오면 waypoints_loaded를 아무도 못 받는다).
        self.nav_panel.try_autoload()

        self.ros_thread.node_ready.connect(self._on_node_ready)
        self.ros_thread.start()

        self.log_panel.add_event("INFO", "대시보드를 시작했습니다.")

    def _connect_signals(self):
        self.bridge.battery_updated.connect(self._on_battery)
        self.bridge.odom_updated.connect(self.status_panel.set_odom)
        self.bridge.scan_updated.connect(self._on_scan)
        self.bridge.link_state_changed.connect(self._on_link_state_changed)
        self.bridge.log_event.connect(self.log_panel.add_event)
        self.bridge.nav_status_changed.connect(self.nav_panel.set_status)
        self.bridge.nav_feedback.connect(self._on_nav_feedback)
        self.bridge.waypoint_progress.connect(self._on_waypoint_progress)
        self.bridge.amcl_pose_updated.connect(self.map_panel.set_robot_pose)

        self.control_panel.velocity_requested.connect(self._on_velocity_requested)
        self.control_panel.log_requested.connect(self.log_panel.add_event)

        self.nav_panel.navigate_requested.connect(self._on_navigate_requested)
        self.nav_panel.follow_requested.connect(self._on_follow_requested)
        self.nav_panel.cancel_requested.connect(self._on_cancel_requested)
        self.nav_panel.log_requested.connect(self.log_panel.add_event)
        self.nav_panel.waypoints_loaded.connect(self._on_nav_waypoints_loaded)
        self.nav_panel.active_waypoint_changed.connect(self.map_panel.set_active_waypoint)
        self.nav_panel.nav_speed_limit_changed.connect(self._on_nav_speed_limit_changed)

        self.map_panel.log_requested.connect(self.log_panel.add_event)
        self.map_panel.saved_to.connect(self.nav_panel.load_from_path)
        self.map_panel.initial_pose_requested.connect(self._on_initial_pose_requested)

        self.ssh_panel.log_requested.connect(self.log_panel.add_event)

    def _on_node_ready(self):
        self._update_header()

    def _robot_ready_state(self) -> str:
        """odom/battery/lidar 토픽 수신 상태를 종합해 로봇 제어 가능 여부를 판단.

        하나라도 완전히 끊겼으면(down) 상태를 못 받아오는 것이니 'down',
        끊긴 건 없지만 일부가 불안정하면 'partial', 전부 정상이면 'up'.
        """
        states = self._link_status.values()
        if any(s == 'down' for s in states):
            return 'down'
        if any(s == 'unstable' for s in states):
            return 'partial'
        return 'up'

    def _update_header(self):
        model = os.environ.get("TURTLEBOT3_MODEL", "알 수 없음")
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        down = [LINK_NAME_KO[k] for k, state in self._link_status.items() if state == 'down']
        unstable = [LINK_NAME_KO[k] for k, state in self._link_status.items() if state == 'unstable']
        if not down and not unstable:
            state_text = "모든 토픽 정상 수신 중"
        else:
            parts = []
            if down:
                parts.append(f"연결 끊김: {', '.join(down)}")
            if unstable:
                parts.append(f"연결 이상: {', '.join(unstable)}")
            state_text = " / ".join(parts)
        self.header_label.setText(
            f"모델: {model}  |  ROS_DOMAIN_ID: {domain_id}  |  {state_text}"
        )

    def _on_battery(self, percentage: float, voltage: float):
        self.status_panel.set_battery(percentage, voltage)
        if percentage <= LOW_BATTERY_THRESHOLD:
            if not self._battery_low_notified:
                self._battery_low_notified = True
                self.log_panel.add_event(
                    "WARN", f"배터리 잔량이 낮습니다: {percentage * 100:.0f}%"
                )
        else:
            self._battery_low_notified = False

    def _on_scan(self, min_range: float):
        self.status_panel.set_scan_min(min_range)
        if not math.isinf(min_range) and min_range < OBSTACLE_WARN_DISTANCE_M:
            if not self._obstacle_notified:
                self._obstacle_notified = True
                self.log_panel.add_event(
                    "WARN", f"장애물이 가까이 있습니다: {min_range:.2f} m"
                )
        else:
            self._obstacle_notified = False

    _LINK_STATE_LOG = {
        'up': ("INFO", "연결됨"),
        'unstable': ("WARN", "연결 불안정 (수신 지연)"),
        'down': ("ERROR", "연결 끊김"),
    }

    def _on_link_state_changed(self, key: str, state: str):
        self.status_panel.set_link_state(key, state)
        self._link_status[key] = state
        self._update_header()
        self.ssh_panel.set_robot_status(self._robot_ready_state())
        name = LINK_NAME_KO.get(key, key)
        level, text = self._LINK_STATE_LOG.get(state, ("ERROR", state))
        self.log_panel.add_event(level, f"{name} {text}")

    def _on_velocity_requested(self, linear: float, angular: float):
        node = self.ros_thread.node
        if node is not None:
            node.send_velocity(linear, angular)

    def _on_navigate_requested(self, x: float, y: float, yaw: float, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.navigate_to_pose(x, y, yaw, frame_id)

    def _on_follow_requested(self, poses: list, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.follow_waypoints(poses, frame_id)

    def _on_cancel_requested(self):
        node = self.ros_thread.node
        if node is not None:
            node.cancel_current_goal()

    def _on_nav_speed_limit_changed(self, percentage: float):
        node = self.ros_thread.node
        if node is not None:
            node.set_nav_speed_limit(percentage)

    def _on_initial_pose_requested(self, x: float, y: float, yaw: float, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.publish_initial_pose(x, y, yaw, frame_id)

    def _on_nav_feedback(self, distance_remaining: float):
        self.nav_panel.set_status(f"목적지까지 남은 거리: {distance_remaining:.2f} m")

    def _on_waypoint_progress(self, current: int, total: int):
        self.nav_panel.set_status(f"경로 주행 중 ({current}/{total})")
        name = self.nav_panel.waypoint_name_at(current)
        if name:
            self.map_panel.set_active_waypoint(name)

    def _on_nav_waypoints_loaded(self, path: str):
        # "웨이포인트 주행" 탭에서 불러온 waypoint를 지도 탭에도 동기화해서,
        # 어떤 지점으로 주행하는지 지도에서 바로 확인할 수 있게 한다.
        self.map_panel.merge_waypoints_from_file(path, quiet=True)

    def closeEvent(self, event):
        node = self.ros_thread.node
        if node is not None:
            node.stop_robot()
        self.ros_thread.stop()
        # 로컬 SSH 작업 스레드만 정리 — 로봇의 원격 bringup은 그대로 계속 실행됨
        self.ssh_panel.wait_for_pending_ssh()
        super().closeEvent(event)
