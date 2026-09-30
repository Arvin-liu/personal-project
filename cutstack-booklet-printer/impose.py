#!/usr/bin/env python3
# Version: 1.3.0 (2026-04-22 00:00) - generalized 8n-page booklet imposition engine
"""PDF imposition logic for 2x2 booklet output across 8-page sheet groups."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

A4_WIDTH_PT = 595.275590551
A4_HEIGHT_PT = 841.88976378
DEFAULT_OUTPUT_DIR = Path.home() / "cutstack-booklet-printer" / "output"
COLS = 2
ROWS = 2
PAGES_PER_SHEET = COLS * ROWS * 2
POINTS_PER_MM = 72.0 / 25.4
HARD_MARGIN_MM = 7.0
OUTER_MARGIN_X_PT = HARD_MARGIN_MM * POINTS_PER_MM
OUTER_MARGIN_Y_PT = HARD_MARGIN_MM * POINTS_PER_MM
INNER_GAP_X_PT = OUTER_MARGIN_X_PT * 2
INNER_GAP_Y_PT = OUTER_MARGIN_Y_PT * 2


class PDFSelectionError(RuntimeError):
    """Raised when the input PDF is invalid or unavailable."""


class ImpositionError(RuntimeError):
    """Raised when the PDF cannot be imposed."""


@dataclass(slots=True)
class CellRect:
    """A placement rectangle on the output A4 page."""

    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True)
class Placement:
    """A source page placement inside one A4 side."""

    coord: tuple[int, int]
    page_number: int
    rotation_deg: int = 0


@dataclass(slots=True)
class ImpositionResult:
    """Summary of a successful imposition run."""

    source_path: Path
    output_path: Path
    original_pages: int
    padded_pages: int
    sheet_count: int
    status_message: str


def validate_pdf_path(source_path: Path) -> Path:
    """Validate that the chosen file exists and looks like a PDF."""

    path = source_path.expanduser().resolve()
    if not path.exists():
        raise PDFSelectionError(f"文件不存在：{path}")
    if not path.is_file():
        raise PDFSelectionError(f"选择的路径不是文件：{path}")
    if path.suffix.lower() != ".pdf":
        raise PDFSelectionError(f"只能选择 PDF 文件：{path.name}")
    return path


def build_output_path(source_path: Path) -> Path:
    """Build the default output path for the imposed PDF."""

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUTPUT_DIR / f"{source_path.stem}_imposed.pdf"


def get_layout_page_mapping(padded_pages: int, layout_mode: str = "default") -> list[int]:
    """Return the zero-based source-page order for one imposed document.

    The returned sequence is grouped by imposed A4 sheet side:
    recto cells first, then verso cells, repeated once per 8-page sheet group.
    """

    if padded_pages <= 0 or padded_pages % PAGES_PER_SHEET != 0:
        raise ImpositionError("拼版页数必须是 8 的整数倍。")

    mapping: list[int] = []
    sheet_count = padded_pages // PAGES_PER_SHEET

    for sheet_idx in range(sheet_count):
        front_start = sheet_idx * 4
        mapping.extend([
            front_start + 0,
            front_start + 1,
            front_start + 2,
            front_start + 3,
        ])

        if layout_mode == "3a6":
            back_anchor = padded_pages - sheet_idx * 4
            mapping.extend([
                back_anchor - 2,
                back_anchor - 1,
                back_anchor - 4,
                back_anchor - 3,
            ])
        else:
            group_start = sheet_idx * PAGES_PER_SHEET
            mapping.extend([
                group_start + 6,
                group_start + 7,
                group_start + 4,
                group_start + 5,
            ])

    return mapping



def pad_page_count(page_count: int, group_size: int = PAGES_PER_SHEET) -> int:
    """Pad page count to a multiple of 8 pages per duplex A4 sheet."""

    remainder = page_count % group_size
    if remainder == 0:
        return page_count
    return page_count + (group_size - remainder)


def build_cell_rects(
    page_width: float = A4_WIDTH_PT,
    page_height: float = A4_HEIGHT_PT,
    cols: int = COLS,
    rows: int = ROWS,
    outer_margin_x: float = OUTER_MARGIN_X_PT,
    outer_margin_y: float = OUTER_MARGIN_Y_PT,
    inner_gap_x: float = INNER_GAP_X_PT,
    inner_gap_y: float = INNER_GAP_Y_PT,
) -> dict[tuple[int, int], CellRect]:
    """Build 2x2 placement rectangles on the A4 output page."""

    usable_width = page_width - 2 * outer_margin_x - (cols - 1) * inner_gap_x
    usable_height = page_height - 2 * outer_margin_y - (rows - 1) * inner_gap_y
    if usable_width <= 0 or usable_height <= 0:
        raise ImpositionError("A4 页面可用区域不足，无法完成 2×2 拼版。")

    cell_width = usable_width / cols
    cell_height = usable_height / rows
    rects: dict[tuple[int, int], CellRect] = {}

    for col in range(cols):
        for row in range(rows):
            x = outer_margin_x + col * (cell_width + inner_gap_x)
            y = outer_margin_y + (rows - 1 - row) * (cell_height + inner_gap_y)
            rects[(col, row)] = CellRect(x=x, y=y, width=cell_width, height=cell_height)

    return rects


def normalize_page_rotation(page) -> None:
    """Flatten page rotation into its content stream before scaling."""

    rotation = getattr(page, "rotation", 0) or 0
    if rotation % 360 != 0 and hasattr(page, "transfer_rotation_to_content"):
        page.transfer_rotation_to_content()


def place_page(dest_page, source_page, rect: CellRect, rotation_deg: int = 0) -> None:
    """Scale a source page to fit inside the target cell and center it."""

    normalize_page_rotation(source_page)
    media_box = source_page.mediabox
    src_left = float(media_box.left)
    src_bottom = float(media_box.bottom)
    src_width = float(media_box.width)
    src_height = float(media_box.height)

    if src_width <= 0 or src_height <= 0:
        raise ImpositionError("检测到尺寸无效的 PDF 页面。")
    if rotation_deg not in (0, 180):
        raise ImpositionError(f"暂不支持的旋转角度：{rotation_deg}")

    scale = min(rect.width / src_width, rect.height / src_height)
    target_width = src_width * scale
    target_height = src_height * scale

    if rotation_deg == 0:
        translate_x = rect.x + (rect.width - target_width) / 2 - src_left * scale
        translate_y = rect.y + (rect.height - target_height) / 2 - src_bottom * scale
        transform = Transformation().scale(scale, scale).translate(translate_x, translate_y)
    else:
        translate_x = rect.x + (rect.width - target_width) / 2 + target_width
        translate_y = rect.y + (rect.height - target_height) / 2 + target_height
        transform = (
            Transformation()
            .translate(-src_left, -src_bottom)
            .scale(scale, scale)
            .rotate(rotation_deg)
            .translate(translate_x, translate_y)
        )
    dest_page.merge_transformed_page(source_page, transform)


def iter_flip_booklet_sheet_maps(
    padded_pages: int,
    layout_mode: str = "default",
) -> tuple[int, list[tuple[list[Placement], list[Placement]]]]:
    """Return repeated A4 front/back placements for each 8-page sheet group.

    Args:
        padded_pages: Total number of padded pages (must be multiple of 8).
        layout_mode: "default" for classic 1234/7856 layout,
                    "3a6" for 3A6 optimized booklet layout.

    Layout modes:
    - "default": Each duplex A4 sheet uses classic 1234 / 7856 layout.
    - "3a6": Front sides still advance 1234, 5678, 9ABC...
      while back sides mirror from the tail of the full 8n-page document:
      for sheet index s, verso = [N-4s-1, N-4s, N-4s-3, N-4s-2].
      This reproduces the measured 8-page order 1234 / 7856 and the
      32-page order 1234 / 31322930 / 5678 / 27282526 / ...
    """

    if padded_pages <= 0 or padded_pages % PAGES_PER_SHEET != 0:
        raise ImpositionError("拼版页数必须是 8 的整数倍。")

    page_offsets = get_layout_page_mapping(padded_pages, layout_mode=layout_mode)
    sheet_maps: list[tuple[list[Placement], list[Placement]]] = []

    for offset_index in range(0, len(page_offsets), PAGES_PER_SHEET):
        recto_offsets = page_offsets[offset_index: offset_index + 4]
        verso_offsets = page_offsets[offset_index + 4: offset_index + 8]
        recto = [
            Placement(coord=(0, 0), page_number=recto_offsets[0] + 1),
            Placement(coord=(1, 0), page_number=recto_offsets[1] + 1),
            Placement(coord=(0, 1), page_number=recto_offsets[2] + 1),
            Placement(coord=(1, 1), page_number=recto_offsets[3] + 1),
        ]
        verso = [
            Placement(coord=(0, 0), page_number=verso_offsets[0] + 1),
            Placement(coord=(1, 0), page_number=verso_offsets[1] + 1),
            Placement(coord=(0, 1), page_number=verso_offsets[2] + 1),
            Placement(coord=(1, 1), page_number=verso_offsets[3] + 1),
        ]
        sheet_maps.append((recto, verso))

    return len(sheet_maps), sheet_maps


def copy_pdf_metadata(reader: PdfReader, writer: PdfWriter) -> None:
    """Copy readable string metadata into the output file."""

    metadata = {}
    if reader.metadata:
        for key, value in reader.metadata.items():
            if not key or value is None:
                continue
            metadata[str(key)] = str(value)
    metadata["/Producer"] = "cutstack-booklet-printer"
    writer.add_metadata(metadata)


def impose_cutstack_pdf(
    source_path: Path,
    output_path: Path | None = None,
    layout_mode: str = "default",
) -> ImpositionResult:
    """Impose a PDF into duplex A4 booklet sheets using 8-page groups.

    Args:
        source_path: Path to the input PDF file.
        output_path: Optional custom output path.
        layout_mode: "default" for classic layout, "3a6" for optimized 3A6 layout.
    """

    validated_source = validate_pdf_path(source_path)
    destination = (output_path or build_output_path(validated_source)).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(validated_source))
    except Exception as exc:  # pragma: no cover - library-specific failures
        raise ImpositionError(f"无法读取 PDF：{validated_source}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            decrypt_result = reader.decrypt("")
        except Exception as exc:  # pragma: no cover - encrypted error path
            raise ImpositionError("不支持受密码保护的 PDF。") from exc
        if decrypt_result == 0:
            raise ImpositionError("不支持受密码保护的 PDF。")

    original_pages = len(reader.pages)
    if original_pages == 0:
        raise ImpositionError("PDF 没有任何页面。")

    padded_pages = pad_page_count(original_pages)
    sheet_count, sheet_maps = iter_flip_booklet_sheet_maps(padded_pages, layout_mode=layout_mode)
    cell_rects = build_cell_rects()

    writer = PdfWriter()
    copy_pdf_metadata(reader, writer)

    try:
        for recto_map, verso_map in sheet_maps:
            recto_page = writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
            for placement in recto_map:
                if placement.page_number > original_pages:
                    continue
                place_page(
                    recto_page,
                    reader.pages[placement.page_number - 1],
                    cell_rects[placement.coord],
                    placement.rotation_deg,
                )

            verso_page = writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
            for placement in verso_map:
                if placement.page_number > original_pages:
                    continue
                place_page(
                    verso_page,
                    reader.pages[placement.page_number - 1],
                    cell_rects[placement.coord],
                    placement.rotation_deg,
                )

        with destination.open("wb") as output_stream:
            writer.write(output_stream)
    except Exception as exc:  # pragma: no cover - library-specific failures
        raise ImpositionError(f"拼版失败：{exc}") from exc

    if layout_mode == "3a6":
        layout_info = "3A6"
    else:
        layout_info = "1234 / 7856"

    status = (
        f"拼版完成：原始 {original_pages} 页，补齐到 {padded_pages} 页，"
        f"每张 A4 双面纸按 {layout_info} 拼版，输出 {sheet_count} 张 A4 双面纸。"
    )
    return ImpositionResult(
        source_path=validated_source,
        output_path=destination,
        original_pages=original_pages,
        padded_pages=padded_pages,
        sheet_count=sheet_count,
        status_message=status,
    )
