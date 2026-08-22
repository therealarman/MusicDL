BG = "#0d1117"
SURFACE = "#161b22"
SURFACE2 = "#1c2130"
BORDER = "#30363d"
ACCENT = "#1db954"
ACCENT_DIM = "#158a3e"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ERROR = "#f85149"
WARN = "#d29922"
INFO = "#58a6ff"

# Per-variant button stylesheets (applied directly so Fusion style doesn't block hover)
def btn_style(variant: str = "secondary", small: bool = False) -> str:
    pad = "5px 10px" if small else "9px 18px"
    fs  = "12px"    if small else "13px"
    br  = "6px"     if small else "8px"
    base = f"border-radius: {br}; font-size: {fs}; font-weight: 600; padding: {pad}; border: none;"
    styles = {
        "primary": f"""
            QPushButton {{ {base} background: {ACCENT}; color: #fff; }}
            QPushButton:hover {{ background: {ACCENT_DIM}; }}
            QPushButton:pressed {{ background: #0f6b2e; }}
            QPushButton:disabled {{ background: {ACCENT}; color: rgba(255,255,255,0.35); }}
        """,
        "secondary": f"""
            QPushButton {{ {base} background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; }}
            QPushButton:hover {{ background: {BORDER}; color: {TEXT}; }}
            QPushButton:pressed {{ background: #3d444d; }}
            QPushButton:disabled {{ color: {MUTED}; background: {SURFACE2}; }}
        """,
        "danger": f"""
            QPushButton {{ {base} background: transparent; color: {ERROR}; border: 1px solid {ERROR}; }}
            QPushButton:hover {{ background: rgba(248,81,73,0.12); }}
            QPushButton:pressed {{ background: rgba(248,81,73,0.22); }}
        """,
        "ghost": f"""
            QPushButton {{ {base} background: none; color: {MUTED}; border: 1px dashed {BORDER}; }}
            QPushButton:hover {{ color: {ACCENT}; border-color: {ACCENT}; border-style: dashed; }}
        """,
        "spotify": f"""
            QPushButton {{ {base} background: {SURFACE2}; color: {ACCENT}; border: 1px solid {ACCENT}; }}
            QPushButton:hover {{ background: rgba(29,185,84,0.12); }}
            QPushButton:pressed {{ background: rgba(29,185,84,0.22); }}
        """,
    }
    return styles.get(variant, styles["secondary"])

QSS = f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow {{
    background: {BG};
}}

QWidget {{
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    color: {TEXT};
    background: transparent;
}}

QScrollArea {{
    background: {BG};
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: {BG};
}}

/* ── Scrollbars ───────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ── Card frames ──────────────────────────────────────────────────────── */
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {SURFACE2};
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    font-size: 14px;
    padding: 10px 14px;
    selection-background-color: {ACCENT};
    selection-color: #fff;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled {{
    color: {MUTED};
}}

QLineEdit#template {{
    font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 13px;
    padding: 8px 12px;
}}

/* ── ComboBox ─────────────────────────────────────────────────────────── */
QComboBox {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT};
    font-size: 12px;
    padding: 6px 32px 6px 10px;
    min-width: 90px;
}}
QComboBox:hover {{
    border-color: {MUTED};
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox:disabled {{
    color: {MUTED};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border: none;
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #fff;
    outline: none;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 4px;
}}

/* ── Buttons ──────────────────────────────────────────────────────────── */
QPushButton {{
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 9px 18px;
    border: none;
}}

QPushButton[variant="primary"] {{
    background: {ACCENT};
    color: #fff;
}}
QPushButton[variant="primary"]:hover {{
    background: {ACCENT_DIM};
}}
QPushButton[variant="primary"]:pressed {{
    background: #0f6b2e;
}}
QPushButton[variant="primary"]:disabled {{
    background: {ACCENT};
    color: rgba(255,255,255,0.4);
}}

QPushButton[variant="secondary"] {{
    background: {SURFACE2};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QPushButton[variant="secondary"]:hover {{
    background: {BORDER};
}}
QPushButton[variant="secondary"]:pressed {{
    background: #3d444d;
}}
QPushButton[variant="secondary"]:disabled {{
    color: {MUTED};
}}

QPushButton[variant="danger"] {{
    background: transparent;
    color: {ERROR};
    border: 1px solid {ERROR};
}}
QPushButton[variant="danger"]:hover {{
    background: rgba(248,81,73,0.12);
}}

QPushButton[variant="ghost"] {{
    background: none;
    color: {MUTED};
    border: 1px dashed {BORDER};
    font-size: 12px;
    font-weight: 500;
    padding: 6px 10px;
    border-radius: 6px;
}}
QPushButton[variant="ghost"]:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}

QPushButton[size="sm"] {{
    padding: 5px 10px;
    font-size: 12px;
    border-radius: 6px;
}}

/* ── CheckBox ─────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {MUTED};
    font-size: 12px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1.5px solid {BORDER};
    border-radius: 3px;
    background: {SURFACE2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* ── Progress bars ────────────────────────────────────────────────────── */
QProgressBar {{
    background: {SURFACE2};
    border: none;
    border-radius: 3px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── Table ────────────────────────────────────────────────────────────── */
QTableWidget {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
    color: {TEXT};
    font-size: 12px;
    outline: none;
    selection-background-color: rgba(29,185,84,0.08);
    selection-color: {TEXT};
    alternate-background-color: transparent;
}}
QTableWidget::item {{
    padding: 3px 8px;
    border-bottom: 1px solid {BORDER};
}}
QTableWidget::item:selected {{
    background: rgba(29,185,84,0.08);
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE2};
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background: {SURFACE2};
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* ── Separator ────────────────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {BORDER};
}}

/* ── Splitter ─────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}
QSplitter::handle:hover {{
    background: {ACCENT};
}}

/* ── Action toolbar / footer bar ──────────────────────────────────────── */
QFrame#actionToolbar,
QFrame#footerBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    border-bottom: none;
}}
QFrame#actionToolbar {{
    border-bottom: 1px solid {BORDER};
}}

/* ── Status bar ───────────────────────────────────────────────────────── */
QStatusBar {{
    background: {SURFACE};
    color: {MUTED};
    font-size: 12px;
    border-top: 1px solid {BORDER};
}}

/* ── Tool tip ─────────────────────────────────────────────────────────── */
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""
