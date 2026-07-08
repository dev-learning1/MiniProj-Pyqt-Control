"""waypoint / trajectory YAML 로더.

기대하는 파일 형식:

    frame_id: map
    waypoints:
      wp1: {x: 1.0, y: 0.5, yaw: 0.0}
      wp2: {x: 2.0, y: 1.0, yaw: 1.57}
    trajectories:
      loop1: [wp1, wp2]
"""
import yaml


class WaypointConfigError(Exception):
    pass


def load_waypoint_file(path: str):
    """Returns (frame_id: str, waypoints: dict[str, tuple(x,y,yaw)], trajectories: dict[str, list[str]])"""
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise WaypointConfigError("YAML 최상위는 매핑(딕셔너리)이어야 합니다.")

    frame_id = data.get('frame_id', 'map')

    raw_waypoints = data.get('waypoints') or {}
    if not isinstance(raw_waypoints, dict):
        raise WaypointConfigError("'waypoints' 항목은 이름:좌표 매핑이어야 합니다.")

    waypoints = {}
    for name, v in raw_waypoints.items():
        try:
            x = float(v['x'])
            y = float(v['y'])
            yaw = float(v.get('yaw', 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise WaypointConfigError(f"waypoint '{name}' 형식 오류: {exc}") from exc
        waypoints[name] = (x, y, yaw)

    if not waypoints:
        raise WaypointConfigError("정의된 waypoint가 없습니다.")

    raw_trajectories = data.get('trajectories') or {}
    if not isinstance(raw_trajectories, dict):
        raise WaypointConfigError("'trajectories' 항목은 이름:웨이포인트 목록 매핑이어야 합니다.")

    trajectories = {}
    for name, seq in raw_trajectories.items():
        if not isinstance(seq, (list, tuple)) or not seq:
            raise WaypointConfigError(f"trajectory '{name}'은(는) 비어있지 않은 목록이어야 합니다.")
        unknown = [wp for wp in seq if wp not in waypoints]
        if unknown:
            raise WaypointConfigError(
                f"trajectory '{name}'이(가) 존재하지 않는 waypoint를 참조합니다: {unknown}"
            )
        trajectories[name] = list(seq)

    return frame_id, waypoints, trajectories


def save_waypoint_file(path: str, frame_id: str, waypoints: dict, trajectories: dict):
    """waypoints: dict[str, tuple(x,y,yaw)], trajectories: dict[str, list[str]]"""
    data = {
        'frame_id': frame_id,
        'waypoints': {
            name: {'x': round(x, 4), 'y': round(y, 4), 'yaw': round(yaw, 4)}
            for name, (x, y, yaw) in waypoints.items()
        },
        'trajectories': {name: list(seq) for name, seq in trajectories.items()},
    }
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
