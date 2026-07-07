"""Spacing scale for Traffic Deployer Qt UI — single source for margins and gaps."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout

from core.hardware_profile import is_work_laptop
from ui.simple_mode import COMPACT_UI

# Base scale (px) — 4-point grid
XS = 4
SM = 6
MD = 8
LG = 12
XL = 16

# Work laptops (4 GB / 720p): keep simple mode but give controls room to breathe.
_WL = is_work_laptop()

# Page column (all nav tabs)
PAGE_PAD = LG if _WL else (MD if COMPACT_UI else LG)
PAGE_GAP = MD if _WL else (SM if COMPACT_UI else MD)

# Section cards (section_group inner)
SECTION_PAD = LG if _WL else (MD if COMPACT_UI else LG)
SECTION_GAP = MD if _WL else (XS if COMPACT_UI else MD)

# Install header / stat tiles
CARD_PAD_H = LG if _WL else (MD if COMPACT_UI else LG)
CARD_PAD_V = MD if _WL else (SM if COMPACT_UI else MD)
CARD_INNER_GAP = SM if _WL else (XS if COMPACT_UI else SM)

# Shell chrome
TOPBAR_PAD_H = LG
TOPBAR_PAD_V = SM
TOPBAR_CLUSTER_GAP = SM
NAV_WIDTH = 58
NAV_PAD_H = SM
NAV_PAD_V = MD
NAV_GAP = XS
SIDE_MIN = 420 if _WL else 348
SIDE_MAX = 460 if _WL else 392
SPLIT_DEFAULT = (440, 712) if _WL else (380, 940)

# Horizontal action rows and form grids
ROW_GAP = SM
GRID_GAP = SM


def apply_page_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(PAGE_PAD, PAGE_PAD, PAGE_PAD, PAGE_PAD)
    layout.setSpacing(PAGE_GAP)


def apply_section_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(SECTION_PAD, SECTION_PAD, SECTION_PAD, SECTION_PAD)
    layout.setSpacing(SECTION_GAP)


def apply_card_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(CARD_PAD_H, CARD_PAD_V, CARD_PAD_H, CARD_PAD_V)
    layout.setSpacing(CARD_INNER_GAP)


def apply_row(layout: QHBoxLayout, *, gap: int = ROW_GAP) -> None:
    layout.setSpacing(gap)


def apply_grid(grid: QGridLayout, *, gap: int = GRID_GAP) -> None:
    grid.setHorizontalSpacing(gap)
    grid.setVerticalSpacing(gap)
