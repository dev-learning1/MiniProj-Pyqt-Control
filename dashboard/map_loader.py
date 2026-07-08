"""nav2 map_server 형식(YAML + PGM/PNG) 맵 로더 및 픽셀<->world 좌표 변환.

회전(origin의 theta)은 지원하지 않는다 — 대부분의 map_saver 결과물이 theta=0이며,
class 실습 범위에서는 회전 없는 맵으로 충분하다.
"""
import os
from dataclasses import dataclass

import yaml
from PIL import Image
from PyQt5.QtGui import QImage


@dataclass
class MapMeta:
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    origin_theta: float
    image: QImage
    image_bytes: bytes  # QImage가 참조하는 버퍼가 GC되지 않도록 붙잡아 둔다


def load_map(yaml_path: str) -> MapMeta:
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    if 'image' not in data or 'resolution' not in data:
        raise ValueError("맵 YAML에 'image' 또는 'resolution' 항목이 없습니다.")

    resolution = float(data['resolution'])
    origin = data.get('origin', [0.0, 0.0, 0.0])
    negate = int(data.get('negate', 0))

    base_dir = os.path.dirname(os.path.abspath(yaml_path))
    image_path = os.path.join(base_dir, data['image'])
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"맵 이미지 파일을 찾을 수 없습니다: {image_path}")

    pil_img = Image.open(image_path).convert('L')
    if negate:
        pil_img = Image.eval(pil_img, lambda v: 255 - v)

    width, height = pil_img.size
    image_bytes = pil_img.tobytes()
    qimage = QImage(image_bytes, width, height, width, QImage.Format_Grayscale8)

    return MapMeta(
        width=width,
        height=height,
        resolution=resolution,
        origin_x=float(origin[0]),
        origin_y=float(origin[1]),
        origin_theta=float(origin[2]) if len(origin) > 2 else 0.0,
        image=qimage,
        image_bytes=image_bytes,
    )


def pixel_to_world(col: float, row: float, meta: MapMeta):
    wx = meta.origin_x + (col + 0.5) * meta.resolution
    wy = meta.origin_y + (meta.height - row - 0.5) * meta.resolution
    return wx, wy


def world_to_pixel(wx: float, wy: float, meta: MapMeta):
    col = (wx - meta.origin_x) / meta.resolution - 0.5
    row = meta.height - 0.5 - (wy - meta.origin_y) / meta.resolution
    return col, row
