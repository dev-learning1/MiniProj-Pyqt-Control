"""맵을 불러와 클릭+드래그로 waypoint를 생성하고 trajectory를 구성하는 패널."""
import math
import os

from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QPen, QBrush, QColor, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QComboBox, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QFileDialog, QInputDialog, QMessageBox, QSplitter,
    QRadioButton, QButtonGroup, QScrollArea
)

from dashboard import theme
from dashboard.map_loader import load_map, pixel_to_world, world_to_pixel
from dashboard.waypoints import load_waypoint_file, save_waypoint_file, WaypointConfigError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_MAPS_DIR = os.path.join(PROJECT_ROOT, "maps")
DEFAULT_CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

DISPLAY_SCALE = 2.0        # 화면 확대 배율 (원본 픽셀 = scene 좌표)
CLICK_VS_DRAG_PX = 5.0     # 이 픽셀 이하로 움직이면 '클릭'(yaw=0)으로 간주
ARROW_LENGTH_PX = 14.0

ROBOT_MARKER_RADIUS_PX = 5.0
ROBOT_ARROW_LENGTH_PX = 16.0

MODE_WAYPOINT = "waypoint"
MODE_POSE_ESTIMATE = "pose_estimate"

HINT_TEXT = {
    MODE_WAYPOINT: "맵 위에서 클릭(제자리) 또는 클릭 후 드래그(방향 지정)하면 waypoint가 추가됩니다.",
    MODE_POSE_ESTIMATE: "맵 위에서 클릭 후 드래그해 로봇의 현재 위치와 방향을 지정하면 "
                        "AMCL 초기 위치(/initialpose)로 전송됩니다.",
}


class _MapView(QGraphicsView):
    """클릭+드래그 제스처만 감지해서 (시작점, 끝점)을 scene 좌표로 알려준다."""

    point_picked = pyqtSignal(QPointF, QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._start = None
        self._temp_dot = None
        self._temp_line = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.scene() is not None:
            self._dragging = True
            self._start = self.mapToScene(event.pos())
            pen = QPen(QColor("red"), 1)
            self._temp_dot = self.scene().addEllipse(
                self._start.x() - 2, self._start.y() - 2, 4, 4, pen, QBrush(QColor("red"))
            )
            self._temp_line = self.scene().addLine(
                self._start.x(), self._start.y(), self._start.x(), self._start.y(), pen
            )
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            cur = self.mapToScene(event.pos())
            self._temp_line.setLine(self._start.x(), self._start.y(), cur.x(), cur.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            end = self.mapToScene(event.pos())
            self.scene().removeItem(self._temp_dot)
            self.scene().removeItem(self._temp_line)
            self._temp_dot = None
            self._temp_line = None
            self.point_picked.emit(self._start, end)
        else:
            super().mouseReleaseEvent(event)


class MapPanel(QWidget):
    log_requested = pyqtSignal(str, str)
    saved_to = pyqtSignal(str)  # 저장한 파일 경로
    initial_pose_requested = pyqtSignal(float, float, float, str)  # x, y, yaw, frame_id

    def __init__(self, parent=None):
        super().__init__(parent)

        self._meta = None
        self.mode = MODE_WAYPOINT
        self.waypoints = {}     # name -> (x, y, yaw)
        self.trajectories = {}  # name -> [waypoint 이름, ...]
        self._markers = {}      # name -> [QGraphicsItem, ...]
        self._pose_estimate_items = []
        # "웨이포인트 주행" 탭에서 현재 실제로 향하고 있는 waypoint 이름.
        # 지도에서 이 waypoint만 다른 색으로 강조 표시한다.
        self._active_waypoint_name = None
        # 로봇의 실시간 위치 마커(점 + 방향선). 매번 새로 그리지 않고
        # setRect/setLine으로 위치만 갱신해서 odom/amcl_pose 갱신 빈도에도
        # 부담 없게 한다.
        self._robot_dot = None
        self._robot_line = None

        default_map = os.path.join(DEFAULT_MAPS_DIR, "last_class_map_modi.yaml")

        # --- 맵 불러오기 ---
        self.map_path_edit = QLineEdit(default_map)
        btn_map_browse = QPushButton("찾아보기...")
        btn_map_load = QPushButton("맵 불러오기")
        btn_map_browse.clicked.connect(self._browse_map)
        btn_map_load.clicked.connect(self._load_map)

        map_file_row = QHBoxLayout()
        map_file_row.addWidget(self.map_path_edit)
        map_file_row.addWidget(btn_map_browse)
        map_file_row.addWidget(btn_map_load)
        map_file_box = QGroupBox("맵 파일 (nav2 map_server YAML)")
        map_file_box.setLayout(map_file_row)

        # --- 동작 모드 ---
        self.radio_waypoint = QRadioButton("Waypoint 생성")
        self.radio_pose_estimate = QRadioButton("초기 위치 설정 (2D Pose Estimate)")
        self.radio_waypoint.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.radio_waypoint)
        mode_group.addButton(self.radio_pose_estimate)
        self.radio_waypoint.toggled.connect(self._on_mode_changed)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.radio_waypoint)
        mode_row.addWidget(self.radio_pose_estimate)
        mode_box = QGroupBox("클릭 동작 모드")
        mode_box.setLayout(mode_row)

        # --- 지도 캔버스 ---
        self.scene = QGraphicsScene(self)
        self.view = _MapView(self)
        self.view.setScene(self.scene)
        self.view.point_picked.connect(self._on_point_picked)
        self.hint_label = QLabel(HINT_TEXT[MODE_WAYPOINT])
        self.hint_label.setWordWrap(True)

        canvas_layout = QVBoxLayout()
        canvas_layout.addWidget(mode_box)
        canvas_layout.addWidget(self.hint_label)
        canvas_layout.addWidget(self.view, 1)
        canvas_widget = QWidget()
        canvas_widget.setLayout(canvas_layout)

        # --- 생성된 waypoint 목록 ---
        self.waypoint_list = QListWidget()
        btn_wp_delete = QPushButton("선택 waypoint 삭제")
        btn_wp_delete.clicked.connect(self._delete_selected_waypoint)
        wp_list_layout = QVBoxLayout()
        wp_list_layout.addWidget(self.waypoint_list)
        wp_list_layout.addWidget(btn_wp_delete)
        wp_list_box = QGroupBox("생성된 Waypoint")
        wp_list_box.setLayout(wp_list_layout)

        # --- trajectory 빌더 ---
        self.wp_select_combo = QComboBox()
        btn_traj_add = QPushButton("경로에 추가")
        btn_traj_add.clicked.connect(self._add_to_building_trajectory)
        self.trajectory_build_list = QListWidget()
        btn_traj_remove = QPushButton("선택 제거")
        btn_traj_clear = QPushButton("초기화")
        btn_traj_remove.clicked.connect(self._remove_from_building_trajectory)
        btn_traj_clear.clicked.connect(self.trajectory_build_list.clear)
        self.trajectory_name_edit = QLineEdit()
        self.trajectory_name_edit.setPlaceholderText("trajectory 이름")
        btn_traj_save = QPushButton("Trajectory로 저장")
        btn_traj_save.clicked.connect(self._save_building_trajectory)

        pick_row = QHBoxLayout()
        pick_row.addWidget(self.wp_select_combo)
        pick_row.addWidget(btn_traj_add)

        build_btn_row = QHBoxLayout()
        build_btn_row.addWidget(btn_traj_remove)
        build_btn_row.addWidget(btn_traj_clear)

        name_row = QHBoxLayout()
        name_row.addWidget(self.trajectory_name_edit)
        name_row.addWidget(btn_traj_save)

        traj_build_layout = QVBoxLayout()
        traj_build_layout.addLayout(pick_row)
        traj_build_layout.addWidget(self.trajectory_build_list)
        traj_build_layout.addLayout(build_btn_row)
        traj_build_layout.addLayout(name_row)
        traj_build_box = QGroupBox("Trajectory 만들기 (순서대로 추가)")
        traj_build_box.setLayout(traj_build_layout)

        # --- 생성된 trajectory 목록 ---
        self.trajectory_list = QListWidget()
        btn_traj_delete = QPushButton("선택 trajectory 삭제")
        btn_traj_delete.clicked.connect(self._delete_selected_trajectory)
        traj_list_layout = QVBoxLayout()
        traj_list_layout.addWidget(self.trajectory_list)
        traj_list_layout.addWidget(btn_traj_delete)
        traj_list_box = QGroupBox("생성된 Trajectory")
        traj_list_box.setLayout(traj_list_layout)

        side_layout = QVBoxLayout()
        side_layout.addWidget(wp_list_box)
        side_layout.addWidget(traj_build_box)
        side_layout.addWidget(traj_list_box)
        side_content = QWidget()
        side_content.setLayout(side_layout)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QScrollArea.NoFrame)
        side_scroll.setWidget(side_content)

        splitter = QSplitter()
        splitter.addWidget(canvas_widget)
        splitter.addWidget(side_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # --- 파일 저장 / 병합 불러오기 ---
        self.frame_id_edit = QLineEdit("map")
        btn_merge_load = QPushButton("기존 waypoint 파일 불러오기(병합)")
        btn_save_as = QPushButton("다른 이름으로 저장...")
        btn_merge_load.clicked.connect(self._merge_load_waypoint_file)
        btn_save_as.clicked.connect(self._save_as)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("frame_id:"))
        save_row.addWidget(self.frame_id_edit)
        save_row.addWidget(btn_merge_load)
        save_row.addWidget(btn_save_as)
        save_box = QGroupBox("저장")
        save_box.setLayout(save_row)

        root = QVBoxLayout()
        root.addWidget(map_file_box)
        root.addWidget(splitter, 1)
        root.addWidget(save_box)
        self.setLayout(root)

        if os.path.exists(default_map):
            self._load_map()

    # --- 맵 불러오기 ---
    def _browse_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "맵 YAML 선택", DEFAULT_MAPS_DIR, "YAML Files (*.yaml *.yml)"
        )
        if path:
            self.map_path_edit.setText(path)
            self._load_map()

    def _load_map(self):
        path = self.map_path_edit.text().strip()
        if not path:
            return
        try:
            self._meta = load_map(path)
        except (OSError, ValueError) as exc:
            self.log_requested.emit("ERROR", f"맵을 불러오지 못했습니다: {exc}")
            return

        self.scene.clear()
        self._markers.clear()
        self._pose_estimate_items = []
        self._active_waypoint_name = None
        # scene.clear()가 기존 QGraphicsItem을 전부 삭제하므로, 들고 있던
        # 참조도 같이 비워야 다음 set_robot_pose()에서 죽은 아이템을
        # setRect/setLine으로 건드리는 걸 막을 수 있다.
        self._robot_dot = None
        self._robot_line = None
        self.waypoint_list.clear()
        self.wp_select_combo.clear()
        pixmap = QPixmap.fromImage(self._meta.image)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(0, 0, self._meta.width, self._meta.height)
        self.view.resetTransform()
        self.view.scale(DISPLAY_SCALE, DISPLAY_SCALE)

        if abs(self._meta.origin_theta) > 1e-6:
            self.log_requested.emit(
                "WARN",
                "맵 origin에 회전(theta)이 있어 좌표 변환이 정확하지 않을 수 있습니다.",
            )
        self.log_requested.emit(
            "INFO",
            f"맵을 불러왔습니다: {os.path.basename(path)} "
            f"({self._meta.width}x{self._meta.height}, {self._meta.resolution} m/px)",
        )

    # --- 동작 모드 ---
    def _on_mode_changed(self, waypoint_checked: bool):
        self.mode = MODE_WAYPOINT if waypoint_checked else MODE_POSE_ESTIMATE
        self.hint_label.setText(HINT_TEXT[self.mode])

    # --- 클릭/드래그 처리 ---
    def _on_point_picked(self, start: QPointF, end: QPointF):
        if self._meta is None:
            self.log_requested.emit("WARN", "먼저 맵을 불러오세요.")
            return

        dx_px = end.x() - start.x()
        dy_px = end.y() - start.y()
        if math.hypot(dx_px, dy_px) < CLICK_VS_DRAG_PX:
            yaw = 0.0
        else:
            yaw = math.atan2(-dy_px, dx_px)  # 이미지 행(row) 축은 world y축과 반대 방향

        if self.mode == MODE_POSE_ESTIMATE:
            self._set_initial_pose(start.x(), start.y(), yaw)
            return

        default_name = self._suggest_name()
        name, ok = QInputDialog.getText(
            self, "Waypoint 이름", "이름을 입력하세요:", text=default_name
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        if name in self.waypoints:
            reply = QMessageBox.question(
                self, "덮어쓰기 확인",
                f"'{name}' waypoint가 이미 있습니다. 덮어쓸까요?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        wx, wy = pixel_to_world(start.x(), start.y(), self._meta)
        self.waypoints[name] = (wx, wy, yaw)
        self._draw_marker(name, start.x(), start.y(), yaw)
        self._refresh_waypoint_widgets()
        self.log_requested.emit(
            "INFO", f"waypoint '{name}' 생성: x={wx:.2f}, y={wy:.2f}, yaw={yaw:.2f}"
        )

    def _set_initial_pose(self, col: float, row: float, yaw: float):
        for item in self._pose_estimate_items:
            self.scene.removeItem(item)
        self._pose_estimate_items = []

        pen = QPen(QColor("green"), 2)
        dot = self.scene.addEllipse(col - 4, row - 4, 8, 8, pen, QBrush(QColor("green")))
        dx = math.cos(yaw) * ARROW_LENGTH_PX * 1.5
        dy = -math.sin(yaw) * ARROW_LENGTH_PX * 1.5
        line = self.scene.addLine(col, row, col + dx, row + dy, pen)
        label = self.scene.addText("초기 위치")
        label.setDefaultTextColor(QColor("darkGreen"))
        label.setScale(0.7)
        label.setPos(col + 4, row - 16)
        self._pose_estimate_items = [dot, line, label]

        wx, wy = pixel_to_world(col, row, self._meta)
        frame_id = self.frame_id_edit.text().strip() or "map"
        self.initial_pose_requested.emit(wx, wy, yaw, frame_id)
        self.log_requested.emit(
            "INFO", f"초기 위치 요청: x={wx:.2f}, y={wy:.2f}, yaw={yaw:.2f}"
        )

    def _suggest_name(self) -> str:
        i = len(self.waypoints) + 1
        while f"wp{i}" in self.waypoints:
            i += 1
        return f"wp{i}"

    def _draw_marker(self, name, col, row, yaw):
        for item in self._markers.pop(name, []):
            self.scene.removeItem(item)

        # "웨이포인트 주행" 탭에서 지금 실제로 향하고 있는 waypoint는 눈에 띄게
        # 다른 색/크기로 그려서, 지도만 보고도 로봇이 맞는 방향으로 가고
        # 있는지 바로 확인할 수 있게 한다.
        highlight = name == self._active_waypoint_name
        color = QColor(theme.AMBER_TEXT) if highlight else QColor("red")
        radius = 6 if highlight else 3
        pen_width = 3 if highlight else 2
        arrow_scale = 1.4 if highlight else 1.0

        pen = QPen(color, pen_width)
        dot = self.scene.addEllipse(
            col - radius, row - radius, radius * 2, radius * 2, pen, QBrush(color)
        )
        dx = math.cos(yaw) * ARROW_LENGTH_PX * arrow_scale
        dy = -math.sin(yaw) * ARROW_LENGTH_PX * arrow_scale
        line = self.scene.addLine(col, row, col + dx, row + dy, pen)
        label = self.scene.addText(("▶ " if highlight else "") + name)
        label.setDefaultTextColor(color if highlight else QColor("blue"))
        label.setScale(0.9 if highlight else 0.7)
        label.setPos(col + 4, row - 16)
        self._markers[name] = [dot, line, label]

    def set_active_waypoint(self, name: str):
        """현재 주행 목표 waypoint를 지도에서 강조 표시한다.

        nav_panel이 단일 목적지 주행/경로 주행을 시작하거나 경로 상의
        다음 목표로 넘어갈 때, 그리고 주행이 끝나 대기 상태로 돌아갈 때
        (name="") 호출된다.
        """
        prev = self._active_waypoint_name
        self._active_waypoint_name = name or None
        for changed_name in (prev, self._active_waypoint_name):
            if changed_name and changed_name in self.waypoints and self._meta is not None:
                x, y, yaw = self.waypoints[changed_name]
                col, row = world_to_pixel(x, y, self._meta)
                self._draw_marker(changed_name, col, row, yaw)

    def set_robot_pose(self, x: float, y: float, yaw: float):
        """AMCL이 추정한 로봇의 현재 위치/방향을 지도 위에 실시간으로 표시한다.

        odom이 아니라 amcl_pose(map 좌표계)를 받아서 그린다 — odom은 시간이
        지나면 map과 어긋나(드리프트) 지도 위에서 위치가 실제와 달라 보일 수
        있기 때문이다. Nav2/AMCL이 떠 있지 않으면 이 메서드 자체가 호출되지
        않으므로 마커도 나타나지 않는다.
        """
        if self._meta is None:
            return
        col, row = world_to_pixel(x, y, self._meta)
        dx = math.cos(yaw) * ROBOT_ARROW_LENGTH_PX
        dy = -math.sin(yaw) * ROBOT_ARROW_LENGTH_PX
        r = ROBOT_MARKER_RADIUS_PX

        if self._robot_dot is None:
            color = QColor(theme.ACCENT)
            pen = QPen(color, 2)
            self._robot_dot = self.scene.addEllipse(col - r, row - r, r * 2, r * 2, pen, QBrush(color))
            self._robot_line = self.scene.addLine(col, row, col + dx, row + dy, pen)
            # waypoint 마커/화살표보다 항상 위에 그려지게 한다.
            self._robot_dot.setZValue(10)
            self._robot_line.setZValue(10)
        else:
            self._robot_dot.setRect(col - r, row - r, r * 2, r * 2)
            self._robot_line.setLine(col, row, col + dx, row + dy)

    def _refresh_waypoint_widgets(self):
        self.waypoint_list.clear()
        for name, (x, y, yaw) in sorted(self.waypoints.items()):
            self.waypoint_list.addItem(
                QListWidgetItem(f"{name}  (x={x:.2f}, y={y:.2f}, yaw={yaw:.2f})")
            )
        current = self.wp_select_combo.currentText()
        self.wp_select_combo.clear()
        self.wp_select_combo.addItems(sorted(self.waypoints.keys()))
        idx = self.wp_select_combo.findText(current)
        if idx >= 0:
            self.wp_select_combo.setCurrentIndex(idx)

    def _delete_selected_waypoint(self):
        item = self.waypoint_list.currentItem()
        if item is None:
            return
        name = item.text().split(" ", 1)[0]
        self.waypoints.pop(name, None)
        for gi in self._markers.pop(name, []):
            self.scene.removeItem(gi)
        self._refresh_waypoint_widgets()
        self.log_requested.emit("INFO", f"waypoint '{name}'을(를) 삭제했습니다.")

    # --- trajectory 빌더 ---
    def _add_to_building_trajectory(self):
        name = self.wp_select_combo.currentText()
        if not name:
            return
        self.trajectory_build_list.addItem(QListWidgetItem(name))

    def _remove_from_building_trajectory(self):
        row = self.trajectory_build_list.currentRow()
        if row >= 0:
            self.trajectory_build_list.takeItem(row)

    def _save_building_trajectory(self):
        name = self.trajectory_name_edit.text().strip()
        if not name:
            self.log_requested.emit("ERROR", "trajectory 이름을 입력하세요.")
            return
        seq = [self.trajectory_build_list.item(i).text()
               for i in range(self.trajectory_build_list.count())]
        if not seq:
            self.log_requested.emit("ERROR", "trajectory에 waypoint를 하나 이상 추가하세요.")
            return

        self.trajectories[name] = seq
        self._refresh_trajectory_list()
        self.trajectory_build_list.clear()
        self.trajectory_name_edit.clear()
        self.log_requested.emit("INFO", f"trajectory '{name}' 생성: {' → '.join(seq)}")

    def _refresh_trajectory_list(self):
        self.trajectory_list.clear()
        for name, seq in sorted(self.trajectories.items()):
            self.trajectory_list.addItem(QListWidgetItem(f"{name}: {' → '.join(seq)}"))

    def _delete_selected_trajectory(self):
        item = self.trajectory_list.currentItem()
        if item is None:
            return
        name = item.text().split(":", 1)[0]
        self.trajectories.pop(name, None)
        self._refresh_trajectory_list()
        self.log_requested.emit("INFO", f"trajectory '{name}'을(를) 삭제했습니다.")

    # --- 파일 입출력 ---
    def _merge_load_waypoint_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "waypoint 파일 불러오기", DEFAULT_CONFIG_DIR, "YAML Files (*.yaml *.yml)"
        )
        if not path:
            return
        self.merge_waypoints_from_file(path)

    def merge_waypoints_from_file(self, path: str, quiet: bool = False):
        """YAML의 waypoint/trajectory를 지도 위에 병합해서 표시한다.

        "기존 waypoint 파일 불러오기(병합)" 버튼과, "웨이포인트 주행" 탭에서
        새 파일을 불러왔을 때 지도에 자동으로 동기화하는 용도로 함께 쓰인다.
        quiet=True면 이벤트 로그를 남기지 않는다(자동 동기화 시 nav_panel이
        이미 같은 내용을 로그로 남기므로 중복을 피한다).
        """
        try:
            frame_id, wps, trajs = load_waypoint_file(path)
        except (OSError, WaypointConfigError) as exc:
            self.log_requested.emit("ERROR", f"waypoint 파일을 불러오지 못했습니다: {exc}")
            return

        self.frame_id_edit.setText(frame_id)
        for name, (x, y, yaw) in wps.items():
            self.waypoints[name] = (x, y, yaw)
            if self._meta is not None:
                col, row = world_to_pixel(x, y, self._meta)
                self._draw_marker(name, col, row, yaw)
        self.trajectories.update(trajs)
        self._refresh_waypoint_widgets()
        self._refresh_trajectory_list()
        if not quiet:
            self.log_requested.emit(
                "INFO", f"'{os.path.basename(path)}'에서 waypoint {len(wps)}개, "
                        f"trajectory {len(trajs)}개를 병합했습니다."
            )

    def _save_as(self):
        if not self.waypoints:
            self.log_requested.emit("ERROR", "저장할 waypoint가 없습니다.")
            return
        default_path = os.path.join(DEFAULT_CONFIG_DIR, "waypoints.yaml")
        path, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장", default_path, "YAML Files (*.yaml *.yml)"
        )
        if not path:
            return
        save_waypoint_file(path, self.frame_id_edit.text().strip() or "map",
                            self.waypoints, self.trajectories)
        self.log_requested.emit("INFO", f"waypoint 파일을 저장했습니다: {path}")
        self.saved_to.emit(path)
