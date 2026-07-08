"""Nav2 웨이포인트 / 트래젝토리 주행 패널."""
import os

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QComboBox,
    QPushButton, QLineEdit, QFileDialog
)

from dashboard.waypoints import load_waypoint_file, WaypointConfigError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_YAML_PATH = os.path.join(PROJECT_ROOT, "config", "waypoints.yaml")


class NavPanel(QWidget):
    navigate_requested = pyqtSignal(float, float, float, str)  # x, y, yaw, frame_id
    follow_requested = pyqtSignal(list, str)                   # [(x,y,yaw), ...], frame_id
    cancel_requested = pyqtSignal()
    log_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.frame_id = "map"
        self.waypoints = {}
        self.trajectories = {}

        self.path_edit = QLineEdit(DEFAULT_YAML_PATH)
        btn_browse = QPushButton("찾아보기...")
        btn_reload = QPushButton("불러오기")
        btn_browse.clicked.connect(self._browse)
        btn_reload.clicked.connect(self._reload)

        file_row = QHBoxLayout()
        file_row.addWidget(self.path_edit)
        file_row.addWidget(btn_browse)
        file_row.addWidget(btn_reload)
        file_box = QGroupBox("Waypoint YAML 파일")
        file_box.setLayout(file_row)

        self.waypoint_combo = QComboBox()
        self.waypoint_info_label = QLabel("-")
        btn_nav = QPushButton("단일 목적지 주행")
        btn_nav.clicked.connect(self._on_navigate_clicked)
        self.waypoint_combo.currentTextChanged.connect(self._update_waypoint_info)

        wp_layout = QVBoxLayout()
        wp_layout.addWidget(self.waypoint_combo)
        wp_layout.addWidget(self.waypoint_info_label)
        wp_layout.addWidget(btn_nav)
        wp_box = QGroupBox("Waypoint (/navigate_to_pose)")
        wp_box.setLayout(wp_layout)

        self.trajectory_combo = QComboBox()
        self.trajectory_info_label = QLabel("-")
        btn_follow = QPushButton("경로 주행")
        btn_follow.clicked.connect(self._on_follow_clicked)
        self.trajectory_combo.currentTextChanged.connect(self._update_trajectory_info)

        traj_layout = QVBoxLayout()
        traj_layout.addWidget(self.trajectory_combo)
        traj_layout.addWidget(self.trajectory_info_label)
        traj_layout.addWidget(btn_follow)
        traj_box = QGroupBox("Trajectory (/follow_waypoints)")
        traj_box.setLayout(traj_layout)

        self.status_label = QLabel("대기 중")
        self.status_label.setStyleSheet("font-weight: bold; padding: 4px;")

        btn_stop = QPushButton("중지 (현재 목표 취소)")
        btn_stop.setMinimumHeight(45)
        btn_stop.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold;"
        )
        btn_stop.clicked.connect(self.cancel_requested.emit)

        root = QVBoxLayout()
        root.addWidget(file_box)
        root.addWidget(wp_box)
        root.addWidget(traj_box)
        root.addWidget(self.status_label)
        root.addWidget(btn_stop)
        root.addStretch(1)
        self.setLayout(root)

        self._try_autoload()

    # --- 파일 로드 ---
    def _try_autoload(self):
        if os.path.exists(self.path_edit.text()):
            self._reload()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Waypoint YAML 선택", PROJECT_ROOT, "YAML Files (*.yaml *.yml)"
        )
        if path:
            self.path_edit.setText(path)
            self._reload()

    def load_from_path(self, path: str):
        self.path_edit.setText(path)
        self._reload()

    def _reload(self):
        path = self.path_edit.text().strip()
        if not path:
            return
        try:
            self.frame_id, self.waypoints, self.trajectories = load_waypoint_file(path)
        except (OSError, WaypointConfigError) as exc:
            self.log_requested.emit("ERROR", f"waypoint 파일을 불러오지 못했습니다: {exc}")
            return

        self.waypoint_combo.clear()
        self.waypoint_combo.addItems(sorted(self.waypoints.keys()))
        self.trajectory_combo.clear()
        self.trajectory_combo.addItems(sorted(self.trajectories.keys()))

        self.log_requested.emit(
            "INFO",
            f"waypoint {len(self.waypoints)}개, trajectory {len(self.trajectories)}개를 불러왔습니다. "
            f"(frame_id={self.frame_id})",
        )

    # --- 정보 라벨 갱신 ---
    def _update_waypoint_info(self, name: str):
        wp = self.waypoints.get(name)
        self.waypoint_info_label.setText(
            f"x={wp[0]:.2f}, y={wp[1]:.2f}, yaw={wp[2]:.2f}" if wp else "-"
        )

    def _update_trajectory_info(self, name: str):
        seq = self.trajectories.get(name)
        self.trajectory_info_label.setText(" → ".join(seq) if seq else "-")

    # --- 버튼 동작 ---
    def _on_navigate_clicked(self):
        name = self.waypoint_combo.currentText()
        wp = self.waypoints.get(name)
        if wp is None:
            self.log_requested.emit("ERROR", "선택된 waypoint가 없습니다.")
            return
        x, y, yaw = wp
        self.navigate_requested.emit(x, y, yaw, self.frame_id)

    def _on_follow_clicked(self):
        name = self.trajectory_combo.currentText()
        seq = self.trajectories.get(name)
        if not seq:
            self.log_requested.emit("ERROR", "선택된 trajectory가 없습니다.")
            return
        poses = [self.waypoints[wp_name] for wp_name in seq]
        self.follow_requested.emit(poses, self.frame_id)

    # --- 외부에서 상태 갱신 ---
    def set_status(self, text: str):
        self.status_label.setText(text)
