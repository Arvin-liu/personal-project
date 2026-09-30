#!/usr/bin/env python3
# Version: 1.4.0 (2026-04-22 00:00) - dynamic 8n-page editor document generator
"""Build a printable document from plain editor text."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import sys
import unicodedata

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from impose import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    DEFAULT_OUTPUT_DIR,
    HARD_MARGIN_MM,
    ImpositionError,
    ImpositionResult,
    POINTS_PER_MM,
    build_cell_rects,
    build_output_path,
    impose_cutstack_pdf,
)

_SOURCE_PAGE_RECT = build_cell_rects()[(0, 0)]
SOURCE_PAGE_WIDTH_PT = _SOURCE_PAGE_RECT.width
SOURCE_PAGE_HEIGHT_PT = _SOURCE_PAGE_RECT.height
MIN_TARGET_PAGE_COUNT = 2
DEFAULT_TARGET_PAGE_COUNT = 8
TARGET_PAGE_STEP = 8
NORMAL_PAGE_STEP = 2
PAGE_MODE_CUTSTACK = "cutstack"
PAGE_MODE_A4 = "a4"
HARD_MARGIN_PT = HARD_MARGIN_MM * POINTS_PER_MM
BASE_SIDE_MARGIN_PT = HARD_MARGIN_PT
BASE_VERTICAL_MARGIN_PT = HARD_MARGIN_PT
# Conservative A4 margin floors help keep content inside common printer
# imageable areas. Users should still use the printer's fit-to-printable-area
# option when their device has larger non-printable margins.
A4_PRINT_SAFE_SIDE_MARGIN_PT = 18.0
A4_PRINT_SAFE_VERTICAL_MARGIN_PT = 44.0
MIN_LINE_HEIGHT_RATIO = 1.08
MAX_SIDE_MARGIN_PT = 72.0
MAX_VERTICAL_MARGIN_PT = 72.0
MAX_LINE_HEIGHT_RATIO = 2.0
SIDE_MARGIN_STEP_PT = 0.5
VERTICAL_MARGIN_STEP_PT = 1.0
LINE_HEIGHT_STEP_RATIO = 0.01
BASE_PARAGRAPH_GAP_PT = 0.0
MAX_PARAGRAPH_GAP_PT = 12.0
PARAGRAPH_GAP_STEP_PT = 0.25
BASE_PARAGRAPH_BEFORE_GAP_PT = 0.0
MAX_PARAGRAPH_BEFORE_GAP_PT = 12.0
PARAGRAPH_BEFORE_GAP_STEP_PT = 0.25
BASE_CHAR_SPACING_PT = 0.0
MAX_CHAR_SPACING_PT = 1.0
CHAR_SPACING_STEP_PT = 0.01
BASE_WORD_SPACING_PT = 0.0
MAX_WORD_SPACING_PT = 2.0
WORD_SPACING_STEP_PT = 0.05
FONT_SEARCH_MIN_PT = 1.0
FONT_SEARCH_START_MAX_PT = 72.0
FONT_SEARCH_LIMIT_PT = 320.0
FONT_SEARCH_STEP_PT = 0.25
DEFAULT_LATIN_SCALE = 1.0
DEFAULT_CJK_SCALE = 0.7
MAX_LATIN_SCALE = 1.18
MIN_CJK_SCALE = 0.58
LATIN_SCALE_STEP = 0.02
CJK_SCALE_STEP = 0.02
BAYES_FONT_SIZE_PRIOR_MEAN_PT = 11.0
BAYES_FONT_SIZE_PRIOR_SIGMA_PT = 4.0
BAYES_FONT_SIZE_OBSERVATION_SIGMA_PT = 1.35
BAYES_FONT_SIZE_RECENCY_DECAY = 0.82
PRIMARY_FONT_NAME = "Project3PrimaryFont"
FALLBACK_FONT_NAME = "Project3FallbackFont"
DEFAULT_SOURCE_FILENAME = "editor_document.pdf"
DEFAULT_PREVIEW_FILENAME = "editor_document_preview_last_page.pdf"
FONT_SIZE_HISTORY_FILENAME = "font_size_history.json"
FONT_SIZE_HISTORY_LIMIT = 24
FOOTER_PADDING_PT = 0.0
FALLBACK_FONT_SIZE_RATIO = 1.0
FIRST_LINE_INDENT_EM = 2.0
MAX_JUSTIFY_EXTRA_CHAR_SPACING_PT = 0.9
TEXT_ALIGNMENT_LEFT = "left"
TEXT_ALIGNMENT_CENTER = "center"
TITLE_FONT_SIZE_SCALE = 1.35

def build_font_candidates() -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Return a platform-aware list of primary and fallback font paths."""

    if sys.platform == "darwin":
        # Use the actual light faces on macOS.  A TTC file is a font collection,
        # so ``get_font_subfont_index`` below selects the light face instead of
        # silently registering the collection's regular face (index 0).
        primary_candidates = (
            Path("/System/Library/Fonts/HelveticaNeue.ttc"),
            Path("/System/Library/Fonts/Helvetica.ttc"),
            Path("/System/Library/Fonts/Arial.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        )
        fallback_candidates = (
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/System/Library/Fonts/Supplemental/PingFang.ttc"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/Apple SD Gothic Neo.ttc"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        )
    else:
        primary_candidates = (
            Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-Th.ttf"),
            Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-L.ttf"),
            Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        )
        fallback_candidates = (
            Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
            Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        )

    return primary_candidates, fallback_candidates

PRIMARY_FONT_CANDIDATES, FALLBACK_FONT_CANDIDATES = build_font_candidates()

_FONT_READY = False


def get_font_subfont_index(font_path: Path) -> int:
    """Return the light face index for a known macOS TrueType collection."""

    light_faces = {
        "HelveticaNeue.ttc": 7,
        "Helvetica.ttc": 4,
        "STHeiti Light.ttc": 1,
    }
    return light_faces.get(font_path.name, 0)


class DocumentBuildError(RuntimeError):
    """Raised when editor text cannot be converted into a printable document."""


@dataclass(slots=True)
class FontPreferences:
    """User-controlled size tuning for Latin and CJK text."""

    latin_scale: float = DEFAULT_LATIN_SCALE
    cjk_scale: float = DEFAULT_CJK_SCALE


@dataclass(slots=True, frozen=True)
class LayoutParameters:
    """Tunables used by the automatic page fitter."""

    side_margin_pt: float = BASE_SIDE_MARGIN_PT
    vertical_margin_pt: float = BASE_VERTICAL_MARGIN_PT
    line_height_ratio: float = MIN_LINE_HEIGHT_RATIO
    paragraph_before_gap_pt: float = BASE_PARAGRAPH_BEFORE_GAP_PT
    paragraph_gap_pt: float = BASE_PARAGRAPH_GAP_PT
    char_spacing_pt: float = BASE_CHAR_SPACING_PT
    word_spacing_pt: float = BASE_WORD_SPACING_PT
    footer_padding_pt: float = FOOTER_PADDING_PT
    @property
    def top_margin_pt(self) -> float:
        """Return the symmetric top margin."""

        return self.vertical_margin_pt

    @property
    def bottom_margin_pt(self) -> float:
        """Return the symmetric bottom margin."""

        return self.vertical_margin_pt


def get_print_safe_layout_parameters(params: LayoutParameters, page_mode: str) -> LayoutParameters:
    """Keep normal A4 content inside the printer's current imageable margins."""

    if page_mode != PAGE_MODE_A4:
        return params

    return replace(
        params,
        side_margin_pt=max(params.side_margin_pt, A4_PRINT_SAFE_SIDE_MARGIN_PT),
        vertical_margin_pt=max(params.vertical_margin_pt, A4_PRINT_SAFE_VERTICAL_MARGIN_PT),
    )


@dataclass(slots=True)
class TextLayout:
    """Computed pagination details for a given font size."""

    font_size: float
    leading: float
    line_capacity: int
    pages: list[list["WrappedLine"]]
    params: LayoutParameters
    preferences: FontPreferences
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT

    @property
    def page_count(self) -> int:
        """Return how many source pages contain text."""

        return len(self.pages)


@dataclass(slots=True)
class WrappedLine:
    """One visual line plus paragraph-boundary metadata."""

    text: str
    paragraph_break_after: bool = False
    paragraph_break_before: bool = False
    first_line_indent_pt: float = 0.0
    alignment: str = TEXT_ALIGNMENT_LEFT
    font_size_scale: float = 1.0
    bold: bool = False


@dataclass(slots=True)
class DocumentBuildResult:
    """Summary of a generated source document and its imposed print PDF."""

    source_path: Path
    imposed_path: Path | None
    font_size: float
    content_pages: int
    output_pages: int
    margin_pt: float
    vertical_margin_pt: float
    line_height_ratio: float
    paragraph_before_gap_pt: float
    paragraph_gap_pt: float
    char_spacing_pt: float
    word_spacing_pt: float
    footer_padding_pt: float
    latin_scale: float
    cjk_scale: float
    status_message: str
    imposition_result: ImpositionResult | None


def ensure_editor_font() -> None:
    """Register deterministic embedded fonts for mixed Latin/CJK text."""

    global _FONT_READY
    if _FONT_READY:
        return

    primary_ready = False
    fallback_ready = False

    for font_path in PRIMARY_FONT_CANDIDATES:
        if not font_path.exists():
            continue
        if font_path.suffix.lower() == ".ttc":
            pdfmetrics.registerFont(
                TTFont(
                    PRIMARY_FONT_NAME,
                    str(font_path),
                    subfontIndex=get_font_subfont_index(font_path),
                )
            )
        else:
            pdfmetrics.registerFont(TTFont(PRIMARY_FONT_NAME, str(font_path)))
        primary_ready = True
        break

    for font_path in FALLBACK_FONT_CANDIDATES:
        if not font_path.exists():
            continue
        if font_path.suffix.lower() == ".ttc":
            pdfmetrics.registerFont(
                TTFont(
                    FALLBACK_FONT_NAME,
                    str(font_path),
                    subfontIndex=get_font_subfont_index(font_path),
                )
            )
        else:
            pdfmetrics.registerFont(TTFont(FALLBACK_FONT_NAME, str(font_path)))
        fallback_ready = True
        break

    if not primary_ready:
        raise DocumentBuildError("未找到 Linux Mint 默认字体文件，无法稳定生成打印 PDF。")
    if not fallback_ready:
        raise DocumentBuildError("未找到可用的中文回退字体文件，无法稳定生成打印 PDF。")

    _FONT_READY = True


def choose_font_for_char(char: str) -> str:
    """Select the embedded font that should render a given character."""

    if char in ("\n", "\r", "\t"):
        return PRIMARY_FONT_NAME
    if ord(char) < 128:
        return PRIMARY_FONT_NAME
    if unicodedata.category(char).startswith("Z"):
        return PRIMARY_FONT_NAME
    return FALLBACK_FONT_NAME


def iter_font_runs(text: str) -> list[tuple[str, str]]:
    """Split text into contiguous runs that share the same embedded font."""

    if not text:
        return []

    runs: list[tuple[str, str]] = []
    current_font = choose_font_for_char(text[0])
    current_text = [text[0]]

    for char in text[1:]:
        font_name = choose_font_for_char(char)
        if font_name == current_font:
            current_text.append(char)
            continue
        runs.append((current_font, "".join(current_text)))
        current_font = font_name
        current_text = [char]

    runs.append((current_font, "".join(current_text)))
    return runs


def get_effective_font_size(
    font_name: str,
    base_font_size: float,
    preferences: FontPreferences,
) -> float:
    """Return the actual drawing size for a given embedded font."""

    if font_name == PRIMARY_FONT_NAME:
        return base_font_size * preferences.latin_scale
    if font_name == FALLBACK_FONT_NAME:
        return base_font_size * FALLBACK_FONT_SIZE_RATIO * preferences.cjk_scale
    return base_font_size


def get_max_effective_font_size(base_font_size: float, preferences: FontPreferences) -> float:
    """Return the largest actual font size used on a line."""

    return max(
        get_effective_font_size(PRIMARY_FONT_NAME, base_font_size, preferences),
        get_effective_font_size(FALLBACK_FONT_NAME, base_font_size, preferences),
    )


def get_wrapped_line_font_size(base_font_size: float, wrapped_line: WrappedLine) -> float:
    """Return the source font size after applying line-specific title styling."""

    return base_font_size * wrapped_line.font_size_scale


def get_wrapped_line_leading(
    base_font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    wrapped_line: WrappedLine,
) -> float:
    """Return vertical advance for a wrapped line, including enlarged titles."""

    return get_max_effective_font_size(
        get_wrapped_line_font_size(base_font_size, wrapped_line),
        preferences,
    ) * params.line_height_ratio


def normalize_editor_text(text: str) -> str:
    """Normalize newline encodings without changing pasted text or blank rows."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise DocumentBuildError("请先输入或粘贴文档内容。")
    return normalized


def _extract_title_block(raw_lines: list[str]) -> tuple[list[str], int] | None:
    """Select only the first text line for visual title styling, unchanged."""

    for cursor, line in enumerate(raw_lines):
        if line.strip():
            return [line], cursor + 1
    return None


def build_editor_source_path() -> Path:
    """Return the stable source PDF path used by the editor workflow."""

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (DEFAULT_OUTPUT_DIR / DEFAULT_SOURCE_FILENAME).resolve()


def build_editor_preview_path() -> Path:
    """Return the stable one-page preview PDF path used by the editor workflow."""

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (DEFAULT_OUTPUT_DIR / DEFAULT_PREVIEW_FILENAME).resolve()


def get_target_page_step(page_mode: str = PAGE_MODE_CUTSTACK) -> int:
    """Return the required page-count multiple for the selected output mode."""

    return NORMAL_PAGE_STEP if page_mode == PAGE_MODE_A4 else TARGET_PAGE_STEP


def get_min_target_page_count(page_mode: str = PAGE_MODE_CUTSTACK) -> int:
    """Return the minimum page target for the selected output mode."""

    return MIN_TARGET_PAGE_COUNT if page_mode == PAGE_MODE_A4 else TARGET_PAGE_STEP


def get_page_dimensions(page_mode: str = PAGE_MODE_CUTSTACK) -> tuple[float, float]:
    """Return source-page dimensions for fitting and rendering."""

    if page_mode == PAGE_MODE_A4:
        return A4_WIDTH_PT, A4_HEIGHT_PT
    return SOURCE_PAGE_WIDTH_PT, SOURCE_PAGE_HEIGHT_PT


def build_editor_a4_output_path() -> Path:
    """Return the stable full-page A4 output path used by the editor workflow."""

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (DEFAULT_OUTPUT_DIR / "editor_document_a4.pdf").resolve()


def normalize_target_page_count(target_pages: int, page_mode: str = PAGE_MODE_CUTSTACK) -> int:
    """Clamp the requested output page count to the selected mode's page groups."""

    normalized_pages = int(target_pages)
    minimum = get_min_target_page_count(page_mode)
    if normalized_pages < minimum:
        return minimum
    step = get_target_page_step(page_mode)
    remainder = normalized_pages % step
    if remainder:
        normalized_pages += step - remainder
    return normalized_pages


def build_font_size_history_path() -> Path:
    """Return the stable history file path for printed font sizes."""

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (DEFAULT_OUTPUT_DIR / FONT_SIZE_HISTORY_FILENAME).resolve()


def load_font_size_history() -> list[float]:
    """Load recent printed base font sizes from disk."""

    history_path = build_font_size_history_path()
    if not history_path.exists():
        return []

    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict):
        return []

    raw_sizes = payload.get("recent_font_sizes", [])
    if not isinstance(raw_sizes, list):
        return []

    history_sizes: list[float] = []
    for raw_size in raw_sizes[:FONT_SIZE_HISTORY_LIMIT]:
        try:
            font_size = round(float(raw_size), 4)
        except (TypeError, ValueError):
            continue
        if FONT_SEARCH_MIN_PT <= font_size <= FONT_SEARCH_LIMIT_PT:
            history_sizes.append(font_size)
    return history_sizes


def record_font_size_history(font_size: float) -> None:
    """Persist a printed base font size so future searches can start nearby."""

    normalized_size = round(float(font_size), 4)
    if not (FONT_SEARCH_MIN_PT <= normalized_size <= FONT_SEARCH_LIMIT_PT):
        return

    history_sizes = [
        size
        for size in load_font_size_history()
        if abs(size - normalized_size) > 1e-6
    ]
    history_sizes.insert(0, normalized_size)
    history_path = build_font_size_history_path()
    payload = {"recent_font_sizes": history_sizes[:FONT_SIZE_HISTORY_LIMIT]}
    try:
        history_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return


def measure_text_width(
    text: str,
    font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
) -> float:
    """Measure text width in points."""

    return _measure_text_width_cached(
        text,
        round(font_size, 4),
        round(preferences.latin_scale, 4),
        round(preferences.cjk_scale, 4),
        round(params.char_spacing_pt, 4),
        round(params.word_spacing_pt, 4),
    )


@lru_cache(maxsize=200000)
def _measure_text_width_cached(
    text: str,
    font_size: float,
    latin_scale: float,
    cjk_scale: float,
    char_spacing_pt: float,
    word_spacing_pt: float,
) -> float:
    """Cached text measurement to keep the automatic fitter responsive."""

    ensure_editor_font()
    preferences = FontPreferences(latin_scale=latin_scale, cjk_scale=cjk_scale)
    base_width = sum(
        pdfmetrics.stringWidth(
            run_text,
            font_name,
            get_effective_font_size(font_name, font_size, preferences),
        )
        for font_name, run_text in iter_font_runs(text)
    )
    char_spacing_width = max(0, len(text) - 1) * char_spacing_pt
    word_spacing_width = text.count(" ") * word_spacing_pt
    return base_width + char_spacing_width + word_spacing_width


def draw_mixed_text_line(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    text: str,
    font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    target_width_pt: float | None = None,
    bold: bool = False,
) -> None:
    """Draw one line using the primary font with CJK fallback."""

    ensure_editor_font()
    char_spacing_pt = params.char_spacing_pt
    if target_width_pt is not None and len(text) > 1:
        text_width = measure_text_width(text, font_size, preferences, params)
        extra_width = target_width_pt - text_width
        extra_char_spacing = extra_width / (len(text) - 1)
        if 0.01 < extra_char_spacing <= MAX_JUSTIFY_EXTRA_CHAR_SPACING_PT:
            char_spacing_pt += extra_char_spacing

    if bold:
        pdf.saveState()
        pdf.setLineWidth(max(0.35, font_size * 0.04))
    text_object = pdf.beginText()
    text_object.setTextOrigin(x, y)
    if bold and hasattr(text_object, "setTextRenderMode"):
        text_object.setTextRenderMode(2)
    if hasattr(text_object, "setCharSpace"):
        text_object.setCharSpace(char_spacing_pt)
    if hasattr(text_object, "setWordSpace"):
        text_object.setWordSpace(params.word_spacing_pt)
    for font_name, run_text in iter_font_runs(text):
        text_object.setFont(
            font_name,
            get_effective_font_size(font_name, font_size, preferences),
        )
        text_object.textOut(run_text)
    pdf.drawText(text_object)
    if bold:
        pdf.restoreState()


def get_footer_reserve_height(
    body_font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
) -> float:
    """Return how much height to reserve for the bottom footer padding."""

    return params.footer_padding_pt


def split_segments(raw_line: str) -> list[str]:
    """Split a line into whitespace, ASCII runs, and single CJK characters."""

    segments: list[str] = []
    index = 0
    length = len(raw_line)

    while index < length:
        char = raw_line[index]
        if char.isspace():
            end = index + 1
            while end < length and raw_line[end].isspace():
                end += 1
            segments.append(raw_line[index:end])
            index = end
            continue

        if ord(char) < 128 and char.isprintable():
            end = index + 1
            while end < length:
                next_char = raw_line[end]
                if next_char.isspace() or ord(next_char) >= 128 or not next_char.isprintable():
                    break
                end += 1
            segments.append(raw_line[index:end])
            index = end
            continue

        segments.append(char)
        index += 1

    return segments


def wrap_single_segment(
    segment: str,
    font_size: float,
    usable_width: float,
    preferences: FontPreferences,
    params: LayoutParameters,
) -> list[str]:
    """Split an oversized token into chunks that fit the page width."""

    pieces: list[str] = []
    current = ""

    for char in segment:
        candidate = current + char
        if current and measure_text_width(candidate, font_size, preferences, params) > usable_width:
            pieces.append(current)
            current = char
            continue
        current = candidate

    if current:
        pieces.append(current)

    return pieces or [""]


def get_first_line_indent_pt(font_size: float, preferences: FontPreferences) -> float:
    """Return the paragraph first-line indent in PDF points."""

    return get_effective_font_size(FALLBACK_FONT_NAME, font_size, preferences) * FIRST_LINE_INDENT_EM


def wrap_line(
    raw_line: str,
    font_size: float,
    usable_width: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    first_line_indent_pt: float = 0.0,
) -> list[str]:
    """Wrap a single editor line into visual lines for the PDF page."""

    if raw_line == "":
        return [""]

    lines: list[str] = []
    current = ""
    current_width_limit = max(1.0, usable_width - first_line_indent_pt)

    for segment in split_segments(raw_line):
        candidate = current + segment
        if not current or measure_text_width(candidate, font_size, preferences, params) <= current_width_limit:
            current = candidate
            continue

        lines.append(current)
        current_width_limit = usable_width
        current = segment

        if measure_text_width(current, font_size, preferences, params) <= usable_width:
            continue

        split_parts = wrap_single_segment(current, font_size, usable_width, preferences, params)
        lines.extend(split_parts[:-1])
        current = split_parts[-1]

    if current or not lines:
        lines.append(current)

    return lines


def build_text_layout(
    text: str,
    font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """Lay out normalized text with the supplied layout parameters."""

    if font_size <= 0:
        raise DocumentBuildError("字号必须大于 0。")

    wrapped_lines = wrap_document_lines(text, font_size, preferences, params, page_width_pt=page_width_pt)
    return paginate_wrapped_lines(
        wrapped_lines,
        font_size,
        preferences,
        params,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )


def wrap_document_lines(
    text: str,
    font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
) -> list[WrappedLine]:
    """Wrap the full document into visual lines for one parameter set."""

    usable_width = page_width_pt - 2 * params.side_margin_pt
    if usable_width <= 0:
        raise DocumentBuildError("页面可用宽度不足，无法排版。")

    wrapped_lines: list[WrappedLine] = []
    raw_lines = text.split("\n")
    title_block = _extract_title_block(raw_lines)
    if title_block is None:
        logical_lines = [(raw_line, False) for raw_line in raw_lines]
        title_index: int | None = None
        first_body_index: int | None = None
    else:
        title_lines, body_start = title_block
        title_index = body_start - 1
        logical_lines = [(raw_line, False) for raw_line in raw_lines[:title_index]]
        logical_lines.append((title_lines[0], True))
        logical_lines.extend((raw_line, False) for raw_line in raw_lines[body_start:])
        first_body_index = next(
            (
                index
                for index in range(title_index + 1, len(logical_lines))
                if logical_lines[index][0].strip()
            ),
            None,
        )

    for raw_index, (raw_line, is_title) in enumerate(logical_lines):
        is_first_body_line = first_body_index is not None and raw_index == first_body_index
        previous_line_is_text = (
            raw_index > 0 and bool(logical_lines[raw_index - 1][0].strip())
        )
        next_line_is_text = (
            raw_index + 1 < len(logical_lines)
            and bool(logical_lines[raw_index + 1][0].strip())
        )
        first_line_indent_pt = (
            0.0
            if is_title or is_first_body_line or not raw_line.strip()
            else get_first_line_indent_pt(font_size, preferences)
        )
        line_font_size = font_size * TITLE_FONT_SIZE_SCALE if is_title else font_size
        visual_lines = wrap_line(
            raw_line,
            line_font_size,
            usable_width,
            preferences,
            params,
            first_line_indent_pt=first_line_indent_pt,
        )
        for visual_index, visual_line in enumerate(visual_lines):
            wrapped_lines.append(
                WrappedLine(
                    text=visual_line,
                    paragraph_break_after=(
                        visual_index == len(visual_lines) - 1
                        and next_line_is_text
                        and not is_title
                    ),
                    paragraph_break_before=(
                        visual_index == 0
                        and bool(raw_line.strip())
                        and previous_line_is_text
                        and not is_title
                    ),
                    first_line_indent_pt=first_line_indent_pt if visual_index == 0 else 0.0,
                    alignment=TEXT_ALIGNMENT_CENTER if is_title else TEXT_ALIGNMENT_LEFT,
                    font_size_scale=TITLE_FONT_SIZE_SCALE if is_title else 1.0,
                    bold=is_title,
                )
            )

    if not wrapped_lines:
        raise DocumentBuildError("文档内容为空，无法排版。")

    return wrapped_lines


def paginate_wrapped_lines(
    wrapped_lines: list[WrappedLine],
    font_size: float,
    preferences: FontPreferences,
    params: LayoutParameters,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """Paginate already-wrapped lines using vertical margins and line height."""

    usable_height = (
        page_height_pt
        - params.top_margin_pt
        - params.bottom_margin_pt
        - get_footer_reserve_height(font_size, preferences, params)
    )
    if usable_height <= 0:
        raise DocumentBuildError("页面可用高度不足，无法排版。")

    leading = get_max_effective_font_size(font_size, preferences) * params.line_height_ratio
    line_capacity = max(1, int(usable_height // leading))

    pages: list[list[WrappedLine]] = [[]]
    used_height = 0.0

    for wrapped_line in wrapped_lines:
        line_leading = get_wrapped_line_leading(font_size, preferences, params, wrapped_line)
        if (
            wrapped_line.paragraph_break_before
            and pages[-1]
            and params.paragraph_before_gap_pt > 0
        ):
            if used_height + params.paragraph_before_gap_pt <= usable_height:
                used_height += params.paragraph_before_gap_pt
            else:
                pages.append([])
                used_height = 0.0

        if used_height + line_leading > usable_height and pages[-1]:
            pages.append([])
            used_height = 0.0

        pages[-1].append(wrapped_line)
        used_height += line_leading

        if wrapped_line.paragraph_break_after and params.paragraph_gap_pt > 0:
            if used_height + params.paragraph_gap_pt <= usable_height:
                used_height += params.paragraph_gap_pt
            elif pages[-1]:
                pages.append([])
                used_height = 0.0

    return TextLayout(
        font_size=round(font_size, 2),
        leading=leading,
        line_capacity=line_capacity,
        pages=pages,
        params=params,
        preferences=preferences,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )


def get_layout_usable_height(layout: TextLayout) -> float:
    """Return the vertical space available for text on one page."""

    return (
        layout.page_height_pt
        - layout.params.top_margin_pt
        - layout.params.bottom_margin_pt
        - get_footer_reserve_height(layout.font_size, layout.preferences, layout.params)
    )


def get_page_content_flow_height(layout: TextLayout, page_lines: list[WrappedLine]) -> float:
    """Return the rendered flow height for a page's text lines."""

    if not page_lines:
        return 0.0

    height = sum(
        get_wrapped_line_leading(layout.font_size, layout.preferences, layout.params, line)
        for line in page_lines
    )
    for index, wrapped_line in enumerate(page_lines):
        if index > 0 and wrapped_line.paragraph_break_before and layout.params.paragraph_before_gap_pt > 0:
            height += layout.params.paragraph_before_gap_pt
        if wrapped_line.paragraph_break_after and layout.params.paragraph_gap_pt > 0:
            height += layout.params.paragraph_gap_pt
    return min(height, get_layout_usable_height(layout))


def get_page_vertical_center_offset(layout: TextLayout, page_lines: list[WrappedLine]) -> float:
    """Return how far to move a page's text down to center it vertically."""

    extra_height = get_layout_usable_height(layout) - get_page_content_flow_height(layout, page_lines)
    return max(0.0, extra_height / 2)


def choose_fitted_layout(
    text: str,
    preferences: FontPreferences,
    params: LayoutParameters | None = None,
    target_pages: int = DEFAULT_TARGET_PAGE_COUNT,
    auto_tune_layout: bool = True,
    page_mode: str = PAGE_MODE_CUTSTACK,
) -> TextLayout:
    """Fit text to the requested page count using ordered typography priorities."""

    page_width_pt, page_height_pt = get_page_dimensions(page_mode)
    base_params = get_print_safe_layout_parameters(params or LayoutParameters(), page_mode)
    base_layout = choose_max_font_layout(text, preferences, base_params, target_pages, page_width_pt, page_height_pt)
    script_tuned_layout = tune_script_scales_without_changing_font(
        text,
        base_layout,
        target_pages,
        page_width_pt,
        page_height_pt,
    )
    if not auto_tune_layout:
        return script_tuned_layout
    return tune_layout_without_changing_font(
        text,
        script_tuned_layout.font_size,
        script_tuned_layout.preferences,
        target_pages,
        base_params=base_params,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )


def choose_max_font_layout(
    text: str,
    preferences: FontPreferences,
    params: LayoutParameters,
    target_pages: int,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """Find the largest English body size at zero margins and minimum line height."""

    history_probes = _build_history_probe_sizes(load_font_size_history())
    best: TextLayout | None = None
    low: float | None = None
    high: float | None = None
    lower_layout: TextLayout | None = None
    upper_layout: TextLayout | None = None

    for probe_size in history_probes:
        layout = build_text_layout(text, probe_size, preferences, params, page_width_pt, page_height_pt)
        if layout.page_count <= target_pages:
            if low is None or probe_size > low:
                low = probe_size
                lower_layout = layout
                best = layout
        else:
            if high is None or probe_size < high:
                high = probe_size
                upper_layout = layout

    if low is None:
        low = FONT_SEARCH_MIN_PT
        lower_layout = build_text_layout(text, low, preferences, params, page_width_pt, page_height_pt)
        while lower_layout.page_count > target_pages and low > 0.1:
            low = round(low / 1.5, 4)
            lower_layout = build_text_layout(text, low, preferences, params, page_width_pt, page_height_pt)

        if lower_layout.page_count > target_pages:
            raise DocumentBuildError(f"内容过长，自动缩小字号后仍无法压到 {target_pages} 页以内。")
        best = lower_layout
    elif best is None and lower_layout is not None:
        best = lower_layout

    if high is None:
        high = max(FONT_SEARCH_START_MAX_PT, low)
        upper_layout = build_text_layout(text, high, preferences, params, page_width_pt, page_height_pt)
        while upper_layout.page_count < target_pages and high < FONT_SEARCH_LIMIT_PT:
            high = min(FONT_SEARCH_LIMIT_PT, round(high * 1.5, 4))
            upper_layout = build_text_layout(text, high, preferences, params, page_width_pt, page_height_pt)

    if best is None:
        best = lower_layout

    for _ in range(24):
        midpoint = (low + high) / 2
        layout = build_text_layout(text, midpoint, preferences, params, page_width_pt, page_height_pt)
        if layout.page_count <= target_pages:
            best = layout
            low = midpoint
        else:
            high = midpoint

    start = max(low, best.font_size - 2.0)
    end = min(high, best.font_size + 2.0)
    probe = start
    while probe <= end + 1e-9:
        layout = build_text_layout(text, probe, preferences, params, page_width_pt, page_height_pt)
        if layout.page_count <= target_pages:
            best = layout
        probe = round(probe + FONT_SEARCH_STEP_PT, 4)

    return best


def _build_history_probe_sizes(history_sizes: list[float]) -> list[float]:
    """Build probe sizes around a Bayesian-weighted font-size posterior."""

    posterior_mean, posterior_sigma = _estimate_history_font_size_posterior(history_sizes)
    normalized_offsets = (0.0, -0.5, 0.5, -1.0, 1.0, -1.5, 1.5, -2.0, 2.0, -3.0, 3.0)
    seen: set[float] = set()
    probes: list[float] = []

    for offset in normalized_offsets:
        candidate = round(posterior_mean + offset * posterior_sigma, 4)
        if not (FONT_SEARCH_MIN_PT <= candidate <= FONT_SEARCH_LIMIT_PT):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        probes.append(candidate)

    # Keep a few exact historical sizes in the queue so abrupt user changes still recover quickly.
    for base_size in history_sizes[:6]:
        for offset in (0.0, -0.5, 0.5, -1.0, 1.0):
            candidate = round(base_size + offset, 4)
            if not (FONT_SEARCH_MIN_PT <= candidate <= FONT_SEARCH_LIMIT_PT):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            probes.append(candidate)

    return probes


def _estimate_history_font_size_posterior(history_sizes: list[float]) -> tuple[float, float]:
    """Estimate a posterior mean/std from printed font-size history with recency decay."""

    prior_precision = 1.0 / (BAYES_FONT_SIZE_PRIOR_SIGMA_PT ** 2)
    weighted_precision_sum = prior_precision
    weighted_mean_sum = BAYES_FONT_SIZE_PRIOR_MEAN_PT * prior_precision

    observation_precision = 1.0 / (BAYES_FONT_SIZE_OBSERVATION_SIGMA_PT ** 2)
    for index, font_size in enumerate(history_sizes[:FONT_SIZE_HISTORY_LIMIT]):
        recency_weight = BAYES_FONT_SIZE_RECENCY_DECAY ** index
        precision = observation_precision * recency_weight
        weighted_precision_sum += precision
        weighted_mean_sum += font_size * precision

    posterior_mean = weighted_mean_sum / weighted_precision_sum
    posterior_sigma = max(0.35, min(2.5, (1.0 / weighted_precision_sum) ** 0.5))
    return posterior_mean, posterior_sigma


def tune_layout_without_changing_font(
    text: str,
    font_size: float,
    preferences: FontPreferences,
    target_pages: int,
    base_params: LayoutParameters | None = None,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """With font fixed, greedily push each layout parameter until the last page overflows."""

    current_params = base_params or LayoutParameters()
    resolved_font_size = round(font_size, 4)
    current_layout = build_text_layout(text, resolved_font_size, preferences, current_params, page_width_pt, page_height_pt)
    while current_layout.page_count > target_pages and resolved_font_size > FONT_SEARCH_MIN_PT:
        resolved_font_size = round(max(FONT_SEARCH_MIN_PT, resolved_font_size - FONT_SEARCH_STEP_PT), 4)
        current_layout = build_text_layout(text, resolved_font_size, preferences, current_params, page_width_pt, page_height_pt)

    tuning_steps = [
        ("paragraph_before_gap_pt", _build_float_range(BASE_PARAGRAPH_BEFORE_GAP_PT, MAX_PARAGRAPH_BEFORE_GAP_PT, PARAGRAPH_BEFORE_GAP_STEP_PT)),
        ("paragraph_gap_pt", _build_float_range(BASE_PARAGRAPH_GAP_PT, MAX_PARAGRAPH_GAP_PT, PARAGRAPH_GAP_STEP_PT)),
        ("line_height_ratio", _build_float_range(MIN_LINE_HEIGHT_RATIO, MAX_LINE_HEIGHT_RATIO, LINE_HEIGHT_STEP_RATIO)),
        ("char_spacing_pt", _build_float_range(BASE_CHAR_SPACING_PT, MAX_CHAR_SPACING_PT, CHAR_SPACING_STEP_PT)),
        ("word_spacing_pt", _build_float_range(BASE_WORD_SPACING_PT, MAX_WORD_SPACING_PT, WORD_SPACING_STEP_PT)),
    ]

    for parameter_name, candidate_values in tuning_steps:
        current_layout = _push_parameter_until_overflow(
            text=text,
            font_size=resolved_font_size,
            preferences=preferences,
            target_pages=target_pages,
            current_layout=current_layout,
            parameter_name=parameter_name,
            candidate_values=candidate_values,
            page_width_pt=page_width_pt,
            page_height_pt=page_height_pt,
        )

    return current_layout


def _push_parameter_until_overflow(
    *,
    text: str,
    font_size: float,
    preferences: FontPreferences,
    target_pages: int,
    current_layout: TextLayout,
    parameter_name: str,
    candidate_values: list[float],
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """Increase one parameter step by step and keep the last non-overflow layout."""

    best_layout = current_layout
    current_value = getattr(current_layout.params, parameter_name)

    for candidate_value in candidate_values:
        if candidate_value <= current_value + 1e-9:
            continue

        params = replace(current_layout.params, **{parameter_name: candidate_value})
        layout = build_text_layout(text, font_size, preferences, params, page_width_pt, page_height_pt)
        if layout.page_count > target_pages:
            break
        best_layout = layout

    return best_layout


def tune_script_scales_without_changing_font(
    text: str,
    base_layout: TextLayout,
    target_pages: int,
    page_width_pt: float = SOURCE_PAGE_WIDTH_PT,
    page_height_pt: float = SOURCE_PAGE_HEIGHT_PT,
) -> TextLayout:
    """Tune Latin/CJK scaling after font size and before geometry changes."""

    best_layout = base_layout
    latin_values = _build_float_range(base_layout.preferences.latin_scale, MAX_LATIN_SCALE, LATIN_SCALE_STEP)
    cjk_values = list(reversed(_build_float_range(MIN_CJK_SCALE, base_layout.preferences.cjk_scale, CJK_SCALE_STEP)))

    for latin_scale in latin_values:
        for cjk_scale in cjk_values:
            if latin_scale == base_layout.preferences.latin_scale and cjk_scale == base_layout.preferences.cjk_scale:
                continue
            preferences = FontPreferences(latin_scale=latin_scale, cjk_scale=cjk_scale)
            layout = build_text_layout(text, base_layout.font_size, preferences, base_layout.params, page_width_pt, page_height_pt)
            if layout.page_count > target_pages:
                continue
            if layout.page_count == target_pages:
                return layout
            if _is_better_script_layout(layout, best_layout):
                best_layout = layout

    return best_layout


def _tune_single_parameter(
    *,
    text: str,
    font_size: float,
    preferences: FontPreferences,
    target_pages: int,
    base_layout: TextLayout,
    parameter_name: str,
    candidate_values: list[float],
) -> TextLayout:
    """Tune one parameter while keeping all higher-priority choices fixed."""

    best_layout = base_layout
    current_value = getattr(base_layout.params, parameter_name)

    for candidate_value in candidate_values:
        if candidate_value < current_value:
            continue
        params = replace(base_layout.params, **{parameter_name: candidate_value})
        layout = build_text_layout(
            text,
            font_size,
            preferences,
            params,
            base_layout.page_width_pt,
            base_layout.page_height_pt,
        )
        if layout.page_count > target_pages:
            continue
        if layout.page_count == target_pages:
            return layout
        if _is_better_underfilled_layout(layout, best_layout):
            best_layout = layout

    return best_layout


def _is_better_underfilled_layout(candidate: TextLayout, current: TextLayout | None) -> bool:
    """Prefer fuller layouts, then lighter-touch parameter changes."""

    if current is None:
        return True
    if candidate.page_count != current.page_count:
        return candidate.page_count > current.page_count

    candidate_signature = (
        candidate.params.side_margin_pt,
        candidate.params.vertical_margin_pt,
        candidate.params.paragraph_before_gap_pt,
        candidate.params.paragraph_gap_pt,
        candidate.params.line_height_ratio,
        candidate.params.char_spacing_pt,
        candidate.params.word_spacing_pt,
        candidate.params.footer_padding_pt,
    )
    current_signature = (
        current.params.side_margin_pt,
        current.params.vertical_margin_pt,
        current.params.paragraph_before_gap_pt,
        current.params.paragraph_gap_pt,
        current.params.line_height_ratio,
        current.params.char_spacing_pt,
        current.params.word_spacing_pt,
        current.params.footer_padding_pt,
    )
    if candidate_signature != current_signature:
        return candidate_signature < current_signature

    return candidate.font_size > current.font_size


def _is_better_script_layout(candidate: TextLayout, current: TextLayout | None) -> bool:
    """Prefer fuller pages, then stronger English emphasis, then smaller Chinese."""

    if current is None:
        return True
    if candidate.page_count != current.page_count:
        return candidate.page_count > current.page_count

    candidate_signature = (
        candidate.preferences.latin_scale,
        -candidate.preferences.cjk_scale,
    )
    current_signature = (
        current.preferences.latin_scale,
        -current.preferences.cjk_scale,
    )
    if candidate_signature != current_signature:
        return candidate_signature > current_signature

    return candidate.font_size > current.font_size


def _build_float_range(start: float, stop: float, step: float) -> list[float]:
    """Return an inclusive float range rounded for stable cache keys."""

    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def render_source_pdf(
    layout: TextLayout,
    output_path: Path,
    total_pages: int,
    page_indices: list[int] | None = None,
) -> Path:
    """Render the fitted text layout into a fixed-count source PDF."""

    ensure_editor_font()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(output_path), pagesize=(layout.page_width_pt, layout.page_height_pt))
    pdf.setAuthor("cutstack-booklet-printer")
    pdf.setCreator("cutstack-booklet-printer")
    pdf.setTitle(f"{total_pages}页文档")
    pdf.setSubject(f"文档编辑器自动生成的 {total_pages} 页源文档")

    for page_index in (page_indices or list(range(total_pages))):
        if page_index < layout.page_count:
            page_lines = layout.pages[page_index]
            vertical_center_offset = get_page_vertical_center_offset(layout, page_lines)
            first_line_font_size = get_max_effective_font_size(
                get_wrapped_line_font_size(layout.font_size, page_lines[0]),
                layout.preferences,
            ) if page_lines else get_max_effective_font_size(layout.font_size, layout.preferences)
            y = (
                layout.page_height_pt
                - layout.params.top_margin_pt
                - vertical_center_offset
                - first_line_font_size
            )
            for line_index, wrapped_line in enumerate(page_lines):
                line_font_size = get_wrapped_line_font_size(layout.font_size, wrapped_line)
                if line_index > 0 and wrapped_line.paragraph_break_before and layout.params.paragraph_before_gap_pt > 0:
                    y -= layout.params.paragraph_before_gap_pt
                if wrapped_line.text:
                    line_x = layout.params.side_margin_pt + wrapped_line.first_line_indent_pt
                    target_width_pt = None
                    if wrapped_line.alignment == TEXT_ALIGNMENT_CENTER:
                        line_x = (
                            layout.page_width_pt
                            - measure_text_width(
                                wrapped_line.text,
                                line_font_size,
                                layout.preferences,
                                layout.params,
                            )
                        ) / 2
                    elif not wrapped_line.paragraph_break_after:
                        target_width_pt = (
                            layout.page_width_pt
                            - 2 * layout.params.side_margin_pt
                            - wrapped_line.first_line_indent_pt
                        )
                    draw_mixed_text_line(
                        pdf,
                        line_x,
                        y,
                        wrapped_line.text,
                        line_font_size,
                        layout.preferences,
                        layout.params,
                        target_width_pt=target_width_pt,
                        bold=wrapped_line.bold,
                    )
                y -= get_wrapped_line_leading(
                    layout.font_size,
                    layout.preferences,
                    layout.params,
                    wrapped_line,
                )
                if wrapped_line.paragraph_break_after and layout.params.paragraph_gap_pt > 0:
                    y -= layout.params.paragraph_gap_pt
        pdf.showPage()

    pdf.save()
    return output_path.resolve()


def build_editor_document(
    text: str,
    preferences: FontPreferences | None = None,
    layout_params: LayoutParameters | None = None,
    target_pages: int = DEFAULT_TARGET_PAGE_COUNT,
    source_path: Path | None = None,
    imposed_path: Path | None = None,
    layout_mode: str = "3a6",
    page_mode: str = PAGE_MODE_CUTSTACK,
    include_imposed_pdf: bool = True,
    auto_tune_layout: bool = True,
    preview_last_page_only: bool = False,
) -> DocumentBuildResult:
    """Convert editor text into a source PDF and the final imposed print PDF.

    Args:
        text: The editor text to be converted to PDF.
        preferences: Optional font size preferences for Latin/CJK scaling.
        layout_params: Optional manual layout parameters that stay fixed during fitting.
        target_pages: Desired source/output page count, rounded to the selected mode's page multiple.
        source_path: Optional custom path for the source PDF.
        imposed_path: Optional custom path for the imposed print PDF.
        layout_mode: "default" for classic 1234/7856 layout, "3a6" for optimized layout.
        include_imposed_pdf: When false, only refresh the source preview PDF.
        auto_tune_layout: When false, only auto-search font size and Latin/CJK scaling.
        preview_last_page_only: When true, render only the last source page into the preview PDF.
    """

    normalized_text = normalize_editor_text(text)
    resolved_target_pages = normalize_target_page_count(target_pages, page_mode=page_mode)
    requested_preferences = preferences or FontPreferences()
    resolved_layout_params = layout_params or LayoutParameters()
    layout = choose_fitted_layout(
        normalized_text,
        requested_preferences,
        params=resolved_layout_params,
        target_pages=resolved_target_pages,
        auto_tune_layout=auto_tune_layout,
        page_mode=page_mode,
    )
    source_pdf = render_source_pdf(
        layout,
        (
            source_path
            or (build_editor_preview_path() if preview_last_page_only and not include_imposed_pdf else build_editor_source_path())
        ).expanduser().resolve(),
        total_pages=resolved_target_pages,
        page_indices=[resolved_target_pages - 1] if preview_last_page_only and not include_imposed_pdf else None,
    )
    print_pdf: Path | None = None
    imposition_result: ImpositionResult | None = None

    if include_imposed_pdf:
        if page_mode == PAGE_MODE_A4:
            print_pdf = source_pdf
        else:
            print_pdf = (imposed_path or build_output_path(source_pdf)).expanduser().resolve()
            try:
                imposition_result = impose_cutstack_pdf(source_pdf, print_pdf, layout_mode=layout_mode)
            except ImpositionError as exc:
                raise DocumentBuildError(f"文档 PDF 已生成，但拼版失败：{exc}") from exc

    if layout.page_count == resolved_target_pages:
        fit_summary = f"正文已铺满 {resolved_target_pages} 页可打印区域"
    else:
        fit_summary = f"正文占用 {layout.page_count}/{resolved_target_pages} 页，剩余页面留白"

    status_parts = [
        f"{fit_summary}，英文字号 {layout.font_size * layout.preferences.latin_scale:.2f} pt，"
        f"中文字号 {layout.font_size * layout.preferences.cjk_scale:.2f} pt，"
        f"侧边距 {layout.params.side_margin_pt:.1f} pt，上下边距 {layout.params.vertical_margin_pt:.1f} pt，"
        f"段前距 {layout.params.paragraph_before_gap_pt:.1f} pt，段后距 {layout.params.paragraph_gap_pt:.1f} pt，"
        f"字距 {layout.params.char_spacing_pt:.2f} pt，词距 {layout.params.word_spacing_pt:.2f} pt，"
        f"行距倍率 {layout.params.line_height_ratio:.2f}，页脚预留 {layout.params.footer_padding_pt:.1f} pt，"
        f"中文 {layout.preferences.cjk_scale * 100:.0f}% ，"
    ]
    if imposition_result is None:
        status_parts.append("双面 A4 PDF 已刷新。" if page_mode == PAGE_MODE_A4 and include_imposed_pdf else "预览 PDF 已刷新。")
    else:
        status_parts.append(f"输出 {imposition_result.sheet_count} 张 A4 双面打印纸。")
    status = "".join(status_parts)

    return DocumentBuildResult(
        source_path=source_pdf,
        imposed_path=print_pdf,
        font_size=layout.font_size,
        content_pages=layout.page_count,
        output_pages=resolved_target_pages,
        margin_pt=layout.params.side_margin_pt,
        vertical_margin_pt=layout.params.vertical_margin_pt,
        line_height_ratio=layout.params.line_height_ratio,
        paragraph_before_gap_pt=layout.params.paragraph_before_gap_pt,
        paragraph_gap_pt=layout.params.paragraph_gap_pt,
        char_spacing_pt=layout.params.char_spacing_pt,
        word_spacing_pt=layout.params.word_spacing_pt,
        footer_padding_pt=layout.params.footer_padding_pt,
        latin_scale=layout.preferences.latin_scale,
        cjk_scale=layout.preferences.cjk_scale,
        status_message=status,
        imposition_result=imposition_result,
    )
