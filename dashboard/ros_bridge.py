"""rclpy <-> Qt 브리지: 터틀봇3 상태 구독 및 cmd_vel 제어."""
import math
import time

import rclpy
import rclpy.executors
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from rclpy.action import ActionClient
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist, PoseStamped, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState, LaserScan
from std_msgs.msg import Empty, Int32
from nav2_msgs.action import NavigateToPose, FollowWaypoints

from PyQt5.QtCore import QObject, QThread, pyqtSignal

_GOAL_STATUS_TEXT = {
    GoalStatus.STATUS_SUCCEEDED: '성공',
    GoalStatus.STATUS_CANCELED: '취소됨',
    GoalStatus.STATUS_ABORTED: '실패(aborted)',
}

# 각 토픽의 마지막 수신으로부터 이 시간(초)이 지나면 "연결 끊김"으로 표시
WATCHDOG_TIMEOUT_SEC = 3.0
# 이 시간(초)이 지나도록 수신이 없으면(끊김까지는 아니지만) "불안정"으로 표시
UNSTABLE_TIMEOUT_SEC = WATCHDOG_TIMEOUT_SEC / 2

# OpenCR 펌웨어의 BatteryState.percentage 필드는 실제 잔량과 무관하게 항상 100%에
# 가깝게 보고되는 알려진 문제가 있어(voltage 필드만 정확), 전압으로 직접 계산한다.
# 3S Li-Po 기준: 완충 12.6V, 안전 방전 컷오프 9.9V
BATTERY_FULL_VOLTAGE = 12.6
BATTERY_EMPTY_VOLTAGE = 9.9

# 전압 센서 노이즈가 그대로 퍼센트로 전달되면 배터리 바가 매 메시지마다 미세하게
# 흔들려 보이므로(떨림), 저역통과 필터로 완만하게 만들어 표시한다. 배터리 잔량은
# 원래 분~시간 단위로 변하는 값이므로 수 초의 시간상수는 체감 반응성에 영향이 없다.
# (메시지 개수 기준 EMA는 토픽 발행 주기가 빠르면 사실상 필터링이 안 되므로,
# 경과 시간 기준으로 계산한다.)
BATTERY_VOLTAGE_TAU_SEC = 5.0


def voltage_to_percentage(voltage: float) -> float:
    if voltage <= 0.0:
        return 0.0
    span = BATTERY_FULL_VOLTAGE - BATTERY_EMPTY_VOLTAGE
    pct = (voltage - BATTERY_EMPTY_VOLTAGE) / span
    return max(0.0, min(1.0, pct))


def quaternion_to_yaw(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def yaw_to_quaternion(yaw: float):
    """평면 주행 가정(roll=pitch=0). Returns (z, w)."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def make_pose_stamped(x: float, y: float, yaw: float, frame_id: str, stamp) -> PoseStamped:
    ps = PoseStamped()
    ps.header.frame_id = frame_id
    ps.header.stamp = stamp
    ps.pose.position.x = float(x)
    ps.pose.position.y = float(y)
    ps.pose.orientation.z, ps.pose.orientation.w = yaw_to_quaternion(yaw)
    return ps


class RosBridge(QObject):
    """rclpy 콜백 스레드에서 GUI 스레드로 데이터를 전달하는 시그널 모음."""

    battery_updated = pyqtSignal(float, float)  # percentage(0-1), voltage(V)
    odom_updated = pyqtSignal(float, float, float, float, float)  # x, y, yaw, lin_vel, ang_vel
    scan_updated = pyqtSignal(float)  # min_range(m)
    link_state_changed = pyqtSignal(str, str)  # topic_name, state('up'/'unstable'/'down')
    log_event = pyqtSignal(str, str)  # level, message

    nav_status_changed = pyqtSignal(str)  # 사람이 읽을 수 있는 주행 상태 문구
    nav_feedback = pyqtSignal(float)  # NavigateToPose: 목적지까지 남은 거리(m)
    waypoint_progress = pyqtSignal(int, int)  # FollowWaypoints: (현재 인덱스, 전체 개수)

    # AMCL이 추정한 로봇의 현재 위치(map 좌표계). /odom은 시간이 지나면 map과
    # 어긋나므로(드리프트) 지도 위에 표시하는 용도로는 쓰지 않는다.
    amcl_pose_updated = pyqtSignal(float, float, float)  # x, y, yaw


class TurtlebotNode(Node):
    def __init__(self, bridge: RosBridge):
        super().__init__('pyqt_dashboard_node')
        self.bridge = bridge

        sensor_qos = QoSProfile(depth=10)
        sensor_qos.reliability = QoSReliabilityPolicy.BEST_EFFORT
        sensor_qos.durability = QoSDurabilityPolicy.VOLATILE

        self._last_seen = {
            'battery_state': None,
            'odom': None,
            'scan': None,
        }
        # 'up' / 'unstable' / 'down' / None(아직 평가 전, 유예 시간 중).
        # None으로 시작해야 유예 시간이 지나 'down'으로 확정될 때 실제로 상태가
        # 바뀐 것으로 인식되어 신호가 발생한다(둘 다 'down'이면 변화가 없다고
        # 판단해 끊김 신호 자체가 발생하지 않는 문제가 있었다).
        self._link_state = {
            'battery_state': None,
            'odom': None,
            'scan': None,
        }
        self._node_start = time.monotonic()
        self._battery_voltage_ema = None
        self._battery_voltage_ema_time = None

        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, 'initialpose', 10
        )

        self._nav_to_pose_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._follow_wp_client = ActionClient(self, FollowWaypoints, 'follow_waypoints')
        self._current_goal_handle = None
        self._wp_total = 0
        self._last_reported_waypoint = 0

        # 로봇(Pi)의 tb3_voice_notifier가 구독해 주행 관련 음성 안내를 재생하는 토픽들.
        self.voice_start_drive_pub = self.create_publisher(Empty, '/voice/start_drive', 10)
        self.voice_waypoint_reached_pub = self.create_publisher(Int32, '/voice/waypoint_reached', 10)
        self.voice_goal_done_pub = self.create_publisher(Empty, '/voice/goal_done', 10)

        self.create_subscription(BatteryState, 'battery_state', self._on_battery, sensor_qos)
        self.create_subscription(Odometry, 'odom', self._on_odom, sensor_qos)
        self.create_subscription(LaserScan, 'scan', self._on_scan, sensor_qos)
        # amcl_pose는 Nav2/AMCL이 떠 있을 때만 발행된다(안 떠 있으면 지도 위
        # 실시간 위치 표시가 그냥 안 나타날 뿐, 연결 끊김 워치독 대상은 아니다).
        self.create_subscription(
            PoseWithCovarianceStamped, 'amcl_pose', self._on_amcl_pose, 10
        )

        self.create_timer(0.5, self._check_watchdog)

    def _touch(self, key):
        self._last_seen[key] = time.monotonic()
        if self._link_state[key] != 'up':
            self._link_state[key] = 'up'
            self.bridge.link_state_changed.emit(key, 'up')

    def _on_battery(self, msg: BatteryState):
        self._touch('battery_state')
        voltage = float(msg.voltage)
        now = time.monotonic()
        if self._battery_voltage_ema is None:
            self._battery_voltage_ema = voltage
        else:
            dt = max(0.0, now - self._battery_voltage_ema_time)
            alpha = 1.0 - math.exp(-dt / BATTERY_VOLTAGE_TAU_SEC)
            self._battery_voltage_ema += alpha * (voltage - self._battery_voltage_ema)
        self._battery_voltage_ema_time = now
        percentage = voltage_to_percentage(self._battery_voltage_ema)
        self.bridge.battery_updated.emit(percentage, self._battery_voltage_ema)

    def _on_odom(self, msg: Odometry):
        self._touch('odom')
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        yaw = quaternion_to_yaw(msg.pose.pose.orientation)
        lin_vel = msg.twist.twist.linear.x
        ang_vel = msg.twist.twist.angular.z
        self.bridge.odom_updated.emit(x, y, yaw, lin_vel, ang_vel)

    def _on_scan(self, msg: LaserScan):
        self._touch('scan')
        valid = [r for r in msg.ranges if msg.range_min <= r <= msg.range_max]
        min_range = min(valid) if valid else float('inf')
        self.bridge.scan_updated.emit(min_range)

    def _on_amcl_pose(self, msg: PoseWithCovarianceStamped):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        yaw = quaternion_to_yaw(msg.pose.pose.orientation)
        self.bridge.amcl_pose_updated.emit(x, y, yaw)

    def _check_watchdog(self):
        now = time.monotonic()
        for key, last in self._last_seen.items():
            if last is None:
                # 기동 후 한 번도 메시지를 받은 적이 없는 경우: 유예 시간 후 끊김 확정.
                # 유예 시간 중에는 상태를 그대로 유지(None)하여 신호를 보내지 않는다.
                if (now - self._node_start) > WATCHDOG_TIMEOUT_SEC:
                    new_state = 'down'
                else:
                    new_state = self._link_state[key]
            else:
                age = now - last
                if age > WATCHDOG_TIMEOUT_SEC:
                    new_state = 'down'
                elif age > UNSTABLE_TIMEOUT_SEC:
                    new_state = 'unstable'
                else:
                    new_state = 'up'
            if new_state != self._link_state[key]:
                self._link_state[key] = new_state
                self.bridge.link_state_changed.emit(key, new_state)

    def send_velocity(self, linear: float, angular: float):
        twist = Twist()
        twist.linear.x = float(linear)
        twist.angular.z = float(angular)
        self.cmd_vel_pub.publish(twist)

    def stop_robot(self):
        self.send_velocity(0.0, 0.0)

    # --- AMCL 초기 위치 설정 (2D Pose Estimate) ---
    def publish_initial_pose(self, x: float, y: float, yaw: float, frame_id: str = 'map'):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = frame_id
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = yaw_to_quaternion(yaw)
        # RViz의 "2D Pose Estimate" 기본 공분산과 동일한 값 사용
        msg.pose.covariance[0] = 0.25       # x
        msg.pose.covariance[7] = 0.25       # y
        msg.pose.covariance[35] = 0.06853891945200942  # yaw

        self.initial_pose_pub.publish(msg)
        self.bridge.log_event.emit(
            "INFO", f"초기 위치를 설정했습니다: x={x:.2f}, y={y:.2f}, yaw={yaw:.2f}"
        )

    # --- Nav2: 단일 목적지 (/navigate_to_pose) ---
    def navigate_to_pose(self, x: float, y: float, yaw: float, frame_id: str = 'map'):
        if not self._nav_to_pose_client.wait_for_server(timeout_sec=1.0):
            self.bridge.log_event.emit('ERROR', 'navigate_to_pose 액션 서버를 찾을 수 없습니다.')
            return
        goal = NavigateToPose.Goal()
        goal.pose = make_pose_stamped(x, y, yaw, frame_id, self.get_clock().now().to_msg())

        self.bridge.log_event.emit('INFO', f'단일 목적지 주행 요청: ({x:.2f}, {y:.2f})')
        self.bridge.nav_status_changed.emit(f'목적지 ({x:.2f}, {y:.2f})로 이동 중...')
        self.voice_start_drive_pub.publish(Empty())

        send_future = self._nav_to_pose_client.send_goal_async(
            goal, feedback_callback=self._on_nav_feedback
        )
        send_future.add_done_callback(self._on_nav_goal_response)

    def _on_nav_feedback(self, feedback_msg):
        self.bridge.nav_feedback.emit(float(feedback_msg.feedback.distance_remaining))

    def _on_nav_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.bridge.log_event.emit('ERROR', '목적지 요청이 거부되었습니다.')
            self.bridge.nav_status_changed.emit('대기 중')
            return
        self._current_goal_handle = goal_handle
        goal_handle.get_result_async().add_done_callback(self._on_nav_result)

    def _on_nav_result(self, future):
        self._current_goal_handle = None
        status = future.result().status
        text = _GOAL_STATUS_TEXT.get(status, f'종료(status={status})')
        level = 'INFO' if status == GoalStatus.STATUS_SUCCEEDED else 'WARN'
        self.bridge.log_event.emit(level, f'단일 목적지 주행 결과: {text}')
        self.bridge.nav_status_changed.emit(f'대기 중 (마지막 결과: {text})')
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.voice_goal_done_pub.publish(Empty())

    # --- Nav2: trajectory (/follow_waypoints) ---
    def follow_waypoints(self, poses, frame_id: str = 'map'):
        if not self._follow_wp_client.wait_for_server(timeout_sec=1.0):
            self.bridge.log_event.emit('ERROR', 'follow_waypoints 액션 서버를 찾을 수 없습니다.')
            return
        stamp = self.get_clock().now().to_msg()
        goal = FollowWaypoints.Goal()
        goal.poses = [make_pose_stamped(x, y, yaw, frame_id, stamp) for (x, y, yaw) in poses]
        self._wp_total = len(goal.poses)
        self._last_reported_waypoint = 0

        self.bridge.log_event.emit('INFO', f'경로 주행 요청: waypoint {self._wp_total}개')
        self.bridge.waypoint_progress.emit(0, self._wp_total)
        self.bridge.nav_status_changed.emit(f'경로 주행 중 (0/{self._wp_total})')
        self.voice_start_drive_pub.publish(Empty())

        send_future = self._follow_wp_client.send_goal_async(
            goal, feedback_callback=self._on_wp_feedback
        )
        send_future.add_done_callback(self._on_wp_goal_response)

    def _on_wp_feedback(self, feedback_msg):
        current = int(feedback_msg.feedback.current_waypoint)
        self.bridge.waypoint_progress.emit(current, self._wp_total)
        # current_waypoint는 "다음에 향할 waypoint의 0-based 인덱스"라, 값이
        # 증가하는 순간이 곧 그 직전 waypoint(1-based로는 새 current 값)에
        # 도착한 시점이다. 같은 waypoint에 대해 중복 안내되지 않도록 증가할
        # 때만 발행한다.
        if current > self._last_reported_waypoint:
            self._last_reported_waypoint = current
            self.voice_waypoint_reached_pub.publish(Int32(data=current))

    def _on_wp_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.bridge.log_event.emit('ERROR', '경로 주행 요청이 거부되었습니다.')
            self.bridge.nav_status_changed.emit('대기 중')
            return
        self._current_goal_handle = goal_handle
        goal_handle.get_result_async().add_done_callback(self._on_wp_result)

    def _on_wp_result(self, future):
        self._current_goal_handle = None
        result = future.result()
        status = result.status
        missed = list(result.result.missed_waypoints)
        if status == GoalStatus.STATUS_SUCCEEDED and not missed:
            self.bridge.log_event.emit('INFO', '경로 주행 완료')
            self.bridge.nav_status_changed.emit('대기 중 (마지막 결과: 성공)')
            self.voice_goal_done_pub.publish(Empty())
        else:
            text = _GOAL_STATUS_TEXT.get(status, f'종료(status={status})')
            detail = f' (놓친 waypoint 인덱스: {missed})' if missed else ''
            self.bridge.log_event.emit('WARN', f'경로 주행 결과: {text}{detail}')
            self.bridge.nav_status_changed.emit(f'대기 중 (마지막 결과: {text})')

    def cancel_current_goal(self):
        if self._current_goal_handle is None:
            self.bridge.log_event.emit('INFO', '취소할 진행 중인 주행이 없습니다.')
            return
        self._current_goal_handle.cancel_goal_async()
        self.bridge.log_event.emit('WARN', '주행 취소를 요청했습니다.')
        self.bridge.nav_status_changed.emit('취소 요청됨...')


class RosThread(QThread):
    """rclpy를 백그라운드 스레드에서 spin. GUI 스레드를 막지 않는다."""

    node_ready = pyqtSignal()

    def __init__(self, bridge: RosBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.node: TurtlebotNode | None = None
        self._running = False

    def run(self):
        rclpy.init(args=None)
        self.node = TurtlebotNode(self.bridge)
        self._running = True
        self.node_ready.emit()
        try:
            while self._running and rclpy.ok():
                try:
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                except rclpy.executors.ExternalShutdownException:
                    break
                except Exception as exc:
                    if not rclpy.ok():
                        # rclpy가 SIGINT/SIGTERM으로 컨텍스트를 먼저 종료한 경우 등
                        break
                    # 콜백 처리 중 일시적 오류: 스레드를 죽이지 말고 계속 진행
                    self.bridge.log_event.emit("ERROR", f"ROS 콜백 처리 오류: {exc}")
        finally:
            self.node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()

    def stop(self):
        self._running = False
        self.wait(2000)
