"""대시보드 공통 디자인 테마.

`.claude/skills/minimalist-ui` 스킬(모노크롬 + 파스텔 포인트 컬러의 에디토리얼
미니멀 스타일)을 Qt 위젯에 맞게 옮기되, 포인트 컬러는 시원한 블루 계열로 잡았다.
"""

# --- 기본 팔레트 (Cool Blue) ------------------------------------------------
BG_CANVAS = "#FFFFFF"       # 창 배경 (흰색)
BG_SURFACE = "#FFFFFF"      # 카드(QGroupBox) 배경
BORDER = "#DFE7EF"          # 카드 테두리 / 구분선 (배경과 카드를 구분)
TEXT_PRIMARY = "#10192B"    # 본문 텍스트 (쿨톤 오프블랙)
TEXT_SECONDARY = "#64748B"  # 보조 텍스트 / 라벨 (슬레이트 블루그레이)

ACCENT = "#2563EB"          # 버튼 등 기본 강조색 (블루)
ACCENT_HOVER = "#1D4ED8"
ACCENT_PRESSED = "#1E40AF"

# --- 상태(의미) 파스텔 컬러: (배경, 텍스트) --------------------------------
GREEN_BG, GREEN_TEXT = "#E3F3EE", "#0F766E"   # 정상 / 연결됨
AMBER_BG, AMBER_TEXT = "#FBF3DB", "#8A6216"   # 주의 / 경고
RED_BG, RED_TEXT = "#FBEAEA", "#A23B34"       # 위험 / 불안정
GRAY_BG, GRAY_TEXT = "#EEF2F6", "#64748B"     # 비활성 / 끊김
BLUE_BG, BLUE_TEXT = "#E5EEFC", "#1D4ED8"     # 정보 (강조색과 통일)

# 안전 관련 버튼(비상 정지 등)은 파스텔로 희석하지 않고 채도를 유지한다.
DANGER_SOLID = "#C0392B"
DANGER_SOLID_HOVER = "#A5311F"

FONT_FAMILY = '"Noto Sans KR", "NanumGothic", "Malgun Gothic", "Segoe UI", sans-serif'
MONO_FONT_FAMILY = '"JetBrains Mono", "D2Coding", "Consolas", "Menlo", monospace'


def pill_qss(bg: str, text: str) -> str:
    """연결 상태 등 작은 배지(pill) 스타일."""
    return (
        f"background-color: {bg}; color: {text}; "
        "padding: 4px 14px; border-radius: 11px; "
        "font-weight: 600; font-size: 11px;"
    )


def mono_label_qss(color: str = TEXT_PRIMARY) -> str:
    """수치 데이터(좌표, 전압 등)에 쓰는 고정폭 라벨 스타일."""
    return f'font-family: {MONO_FONT_FAMILY}; color: {color};'


APP_STYLESHEET = f"""
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: 10pt;
    color: {TEXT_PRIMARY};
}}

QMainWindow, QWidget#Central {{
    background-color: {BG_CANVAS};
}}

QGroupBox {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 11px;
    padding: 10px 8px 6px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 1px;
    padding: 0 4px;
    color: {TEXT_SECONDARY};
    font-weight: 600;
    font-size: 9pt;
}}

QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QPushButton {{
    background-color: {ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background-color: {ACCENT_PRESSED}; }}
QPushButton:disabled {{ background-color: {BORDER}; color: {TEXT_SECONDARY}; }}

QLineEdit, QComboBox {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG_SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SECONDARY};
    padding: 8px 18px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}

QProgressBar {{
    background-color: {BORDER};
    border: none;
    border-radius: 6px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-weight: 600;
    height: 22px;
}}
QProgressBar::chunk {{ border-radius: 6px; }}

QTableWidget {{
    background-color: {BG_SURFACE};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QHeaderView::section {{
    background-color: {BG_CANVAS};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: 600;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
