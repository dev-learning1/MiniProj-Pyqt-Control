"""Nav2 웨이포인트 / 트래젝토리 주행 패널."""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QComboBox,
    QPushButton, QLineEdit, QFileDialog, QScrollArea, QSlider
)

from dashboard import theme
from dashboard.waypoints import load_waypoint_file, WaypointConfigError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_YAML_PATH = os.path.join(PROJECT_ROOT, "config", "waypoints.yaml")


class NavPanel(QWidget):
    navigate_requested = pyqtSignal(float, float, float, str)  # x, y, yaw, frame_id
    follow_requested = pyqtSignal(list, str)                   # [(x,y,yaw), ...], frame_id
    cancel_requested = pyqtSignal()
    log_requested = pyqtSignal(str, str)
    waypoints_loaded = pyqtSignal(str)       # 불러온 파일 경로 (지도 동기화용)
    active_waypoint_changed = pyqtSignal(str)  # 현재 주행 목표 waypoint 이름("" = 없음)
    nav_speed_limit_changed = pyqtSignal(float)  # Nav2 런타임 속도 제한(%)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.frame_id = "map"
        self.waypoints = {}
        self.trajectories = {}
        # /follow_waypoints로 마지막에 보낸 경로의 waypoint 이름 순서.
        # waypoint_progress 피드백의 인덱스로 "지금 향하는 waypoint"를 찾는 데 쓴다.
        self._active_trajectory_seq = []

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

        # Nav2 param YAML(max_vel_x 등)을 고치지 않고, controller_server에
        # 런타임 SpeedLimit을 보내 주행 속도를 즉시 스케일링한다.
        self.nav_speed_slider = QSlider(Qt.Horizontal)
        self.nav_speed_slider.setRange(10, 100)
        self.nav_speed_slider.setValue(100)
        self.nav_speed_label = QLabel("100%  (Nav2 설정값 그대로)")
        self.nav_speed_slider.valueChanged.connect(self._on_nav_speed_changed)

        speed_row = QHBoxLayout()
        speed_row.addWidget(self.nav_speed_slider)
        speed_row.addWidget(self.nav_speed_label)
        speed_layout = QVBoxLayout()
        speed_layout.addLayout(speed_row)
        speed_box = QGroupBox("주행 속도 제한 (%)")
        speed_box.setLayout(speed_layout)

        self.status_label = QLabel("대기 중")
        self.status_label.setStyleSheet(
            f"font-weight: 600; padding: 4px; color: {theme.TEXT_SECONDARY};"
        )

        btn_stop = QPushButton("중지 (현재 목표 취소)")
        btn_stop.setMinimumHeight(45)
        btn_stop.setStyleSheet(
            f"background-color: {theme.DANGER_SOLID}; color: white; font-weight: 700;"
        )
        btn_stop.clicked.connect(self._on_stop_clicked)

        root = QVBoxLayout()
        root.addWidget(file_box)
        root.addWidget(wp_box)
        root.addWidget(traj_box)
        root.addWidget(speed_box)
        root.addWidget(self.status_label)
        root.addWidget(btn_stop)
        root.addStretch(1)

        content = QWidget()
        content.setLayout(root)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    # --- 파일 로드 ---
    def try_autoload(self):
        """시작 시 기본 waypoint 파일을 불러온다.

        main_window가 모든 패널을 만들고 시그널 연결까지 끝낸 뒤 호출해야
        waypoints_loaded 시그널을 map_panel이 놓치지 않고 받아 지도에 동기화된다.
        """
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
        self.waypoints_loaded.emit(path)

    # --- 정보 라벨 갱신 ---
    def _update_waypoint_info(self, name: str):
        wp = self.waypoints.get(name)
        self.waypoint_info_label.setText(
            f"x={wp[0]:.2f}, y={wp[1]:.2f}, yaw={wp[2]:.2f}" if wp else "-"
        )

    def _update_trajectory_info(self, name: str):
        seq = self.trajectories.get(name)
        self.trajectory_info_label.setText(" → ".join(seq) if seq else "-")

    # --- 속도 설정 ---
    def _on_nav_speed_changed(self, value: int):
        if value >= 100:
            self.nav_speed_label.setText("100%  (Nav2 설정값 그대로)")
        else:
            self.nav_speed_label.setText(f"{value}%")
        self.nav_speed_limit_changed.emit(float(value))

    # --- 버튼 동작 ---
    def _on_navigate_clicked(self):
        name = self.waypoint_combo.currentText()
        wp = self.waypoints.get(name)
        if wp is None:
            self.log_requested.emit("ERROR", "선택된 waypoint가 없습니다.")
            return
        x, y, yaw = wp
        self._active_trajectory_seq = []
        self.active_waypoint_changed.emit(name)
        # 슬라이더 값이 이미 실시간으로 반영되고 있지만, 주행 시작 시점에
        # 한 번 더 보내 controller_server가 확실히 최신 값을 갖게 한다.
        self.nav_speed_limit_changed.emit(float(self.nav_speed_slider.value()))
        self.navigate_requested.emit(x, y, yaw, self.frame_id)

    def _on_follow_clicked(self):
        name = self.trajectory_combo.currentText()
        seq = self.trajectories.get(name)
        if not seq:
            self.log_requested.emit("ERROR", "선택된 trajectory가 없습니다.")
            return
        poses = [self.waypoints[wp_name] for wp_name in seq]
        self._active_trajectory_seq = seq
        self.active_waypoint_changed.emit(seq[0])
        self.nav_speed_limit_changed.emit(float(self.nav_speed_slider.value()))
        self.follow_requested.emit(poses, self.frame_id)

    def _on_stop_clicked(self):
        self._active_trajectory_seq = []
        self.active_waypoint_changed.emit("")
        self.cancel_requested.emit()

    # --- 경로 주행 진행 상황 ---
    def waypoint_name_at(self, index: int):
        """현재 보내둔 trajectory에서 index번째 waypoint 이름(없으면 None)."""
        if 0 <= index < len(self._active_trajectory_seq):
            return self._active_trajectory_seq[index]
        return None

    # --- 외부에서 상태 갱신 ---
    def set_status(self, text: str):
        self.status_label.setText(text)
        if text.startswith("대기 중"):
            # ros_bridge는 주행이 성공/취소/실패로 끝나 대기 상태로 돌아갈 때
            # 항상 "대기 중"으로 시작하는 문구를 보낸다. 이 시점에 지도의
            # 목표 강조 표시도 같이 지운다.
            self._active_trajectory_seq = []
            self.active_waypoint_changed.emit("")
