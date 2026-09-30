#!/usr/bin/env python3
# Version: 1.5.0 (2026-04-22 00:00) - dynamic page-count Tkinter editor UI
"""Tkinter editor interface for building a printable cut-and-stack document."""

from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from pathlib import Path
import re
from time import monotonic
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk
from pdf2image import convert_from_path
from pypdf import PdfReader

from editor_document import (
    BASE_CHAR_SPACING_PT,
    FALLBACK_FONT_CANDIDATES,
    FALLBACK_FONT_NAME,
    BASE_PARAGRAPH_BEFORE_GAP_PT,
    BASE_PARAGRAPH_GAP_PT,
    BASE_SIDE_MARGIN_PT,
    BASE_VERTICAL_MARGIN_PT,
    BASE_WORD_SPACING_PT,
    CHAR_SPACING_STEP_PT,
    PAGE_MODE_A4,
    PAGE_MODE_CUTSTACK,
    build_editor_preview_path,
    build_editor_a4_output_path,
    build_editor_source_path,
    build_text_layout,
    choose_fitted_layout,
    DocumentBuildError,
    DocumentBuildResult,
    FontPreferences,
    FOOTER_PADDING_PT,
    get_effective_font_size,
    get_font_subfont_index,
    get_wrapped_line_font_size,
    get_wrapped_line_leading,
    LayoutParameters,
    LINE_HEIGHT_STEP_RATIO,
    get_page_vertical_center_offset,
    MAX_CHAR_SPACING_PT,
    MAX_LINE_HEIGHT_RATIO,
    MAX_PARAGRAPH_BEFORE_GAP_PT,
    MAX_PARAGRAPH_GAP_PT,
    MAX_SIDE_MARGIN_PT,
    MAX_VERTICAL_MARGIN_PT,
    MAX_WORD_SPACING_PT,
    MIN_LINE_HEIGHT_RATIO,
    normalize_target_page_count,
    normalize_editor_text,
    PARAGRAPH_BEFORE_GAP_STEP_PT,
    PARAGRAPH_GAP_STEP_PT,
    PRIMARY_FONT_CANDIDATES,
    PRIMARY_FONT_NAME,
    render_source_pdf,
    get_page_dimensions,
    get_print_safe_layout_parameters,
    get_target_page_step,
    get_min_target_page_count,
    get_max_effective_font_size,
    iter_font_runs,
    MAX_JUSTIFY_EXTRA_CHAR_SPACING_PT,
    measure_text_width,
    SIDE_MARGIN_STEP_PT,
    TARGET_PAGE_STEP,
    TEXT_ALIGNMENT_CENTER,
    VERTICAL_MARGIN_STEP_PT,
    WORD_SPACING_STEP_PT,
    record_font_size_history,
)
from impose import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    DEFAULT_OUTPUT_DIR,
    build_cell_rects,
    build_output_path,
    get_layout_page_mapping,
    impose_cutstack_pdf,
    pad_page_count,
)
from printer import (
    PrintCommandError,
    direct_print_pdf,
    get_poppler_path,
    open_path_with_default_app,
    open_pdf_for_manual_print,
)

CUTSTACK_PRINT_HINT = "打印时不要再开启小册子或多页并打，只需选择 A4 和双面打印。"
A4_DUPLEX_LABEL = "双面 A4 PDF"
A4_PRINT_HINT = "打印方式：双面 A4 PDF，自动适合并居中到打印机可打印区域；选择 A4 和双面（长边翻页），不要开启 booklet 或多页并打。"
AUTO_CLIPBOARD_LOAD_DELAY_MS = 180
MIN_VALIDATION_TOTAL_CHARS = 1800
MIN_VALIDATION_LATIN_CHARS = 180
MIN_VALIDATION_CJK_CHARS = 180

THEME = {
    "shell": "#0c1118",
    "panel": "#141c26",
    "panel_strong": "#101720",
    "page": "#1b2531",
    "page_soft": "#202c3a",
    "border": "#2b3948",
    "ink": "#edf3fb",
    "muted": "#9fb1c4",
    "accent": "#78bfff",
    "accent_strong": "#5ea6ea",
    "accent_soft": "#22364a",
    "button": "#1a2430",
    "button_hover": "#243243",
    "disabled_bg": "#151d26",
    "disabled_fg": "#5f6d7d",
    "selection": "#2e5c82",
    "danger": "#ff8c7a",
    "danger_surface": "#382128",
    "danger_surface_strong": "#4a252d",
    "scroll_thumb": "#3d4754",
    "scroll_thumb_active": "#596473",
}

VIEW_LABELS = {
    "editor": "编辑",
    "preview": "预览",
}

PREVIEW_WATERMARK_FONT_CANDIDATES = tuple(PRIMARY_FONT_CANDIDATES) + (
    *FALLBACK_FONT_CANDIDATES,
    Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)
PREVIEW_WATERMARK_ALPHA = 112
FLOATING_MENU_IMAGE_PATH = Path(__file__).resolve().parent / "assets" / "floating-menu.png"
MAX_TARGET_PAGE_COUNT = 256
DEFAULT_START_PAGE_COUNT = 2


def _convert_pdf_to_images(pdf_path: Path, *, dpi: int = 120) -> list[Image.Image]:
    """Render PDF pages for the in-app preview with a self-contained fallback."""

    poppler_path = get_poppler_path()
    poppler_error: Exception | None = None
    if poppler_path is not None:
        try:
            return convert_from_path(
                str(pdf_path),
                dpi=dpi,
                poppler_path=str(poppler_path),
            )
        except Exception as exc:  # pragma: no cover - depends on local Poppler
            poppler_error = exc

    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError as exc:
            if poppler_error is not None:
                raise RuntimeError(
                    f"Poppler 预览失败：{poppler_error}；PyMuPDF 未安装，请运行 `pip install PyMuPDF`。"
                ) from exc
            raise RuntimeError(
                "未找到 PDF 预览渲染器，请运行 `pip install PyMuPDF`；也可以安装 Poppler：`brew install poppler`。"
            ) from exc

    scale = dpi / 72.0
    images: list[Image.Image] = []
    document = pymupdf.open(str(pdf_path))
    try:
        matrix = pymupdf.Matrix(scale, scale)
        for page in document:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
    finally:
        document.close()

    return images


LAYOUT_CONTROL_DEFS = (
    ("side_margin_pt", "侧边距", BASE_SIDE_MARGIN_PT, MAX_SIDE_MARGIN_PT, SIDE_MARGIN_STEP_PT, "{:.1f} pt"),
    ("vertical_margin_pt", "上下边距", BASE_VERTICAL_MARGIN_PT, MAX_VERTICAL_MARGIN_PT, VERTICAL_MARGIN_STEP_PT, "{:.1f} pt"),
    ("paragraph_before_gap_pt", "段前距", BASE_PARAGRAPH_BEFORE_GAP_PT, MAX_PARAGRAPH_BEFORE_GAP_PT, PARAGRAPH_BEFORE_GAP_STEP_PT, "{:.2f} pt"),
    ("paragraph_gap_pt", "段后距", BASE_PARAGRAPH_GAP_PT, MAX_PARAGRAPH_GAP_PT, PARAGRAPH_GAP_STEP_PT, "{:.2f} pt"),
    ("line_height_ratio", "行距倍率", MIN_LINE_HEIGHT_RATIO, MAX_LINE_HEIGHT_RATIO, LINE_HEIGHT_STEP_RATIO, "{:.2f}"),
    ("char_spacing_pt", "字距", BASE_CHAR_SPACING_PT, MAX_CHAR_SPACING_PT, CHAR_SPACING_STEP_PT, "{:.2f} pt"),
    ("word_spacing_pt", "词距", BASE_WORD_SPACING_PT, MAX_WORD_SPACING_PT, WORD_SPACING_STEP_PT, "{:.2f} pt"),
    ("footer_padding_pt", "页脚预留", FOOTER_PADDING_PT, FOOTER_PADDING_PT + 16.0, 1.0, "{:.1f} pt"),
)


class CutStackBookletPrinterApp:
    """Desktop editor that turns text into a cut-and-stack print PDF."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("多页文档编辑打印工具")
        self.root.geometry("1280x820")
        self.root.minsize(1080, 700)
        self.root.configure(bg=THEME["shell"])
        self._maximize_window()

        self.source_path: Path | None = None
        self.print_source_path: Path | None = None
        self.output_path: Path | None = None
        self.result: DocumentBuildResult | None = None
        self.is_dirty = False
        self.print_pdf_ready = False
        self.layout_mode = "3a6"  # Default layout mode: "default" or "3a6"
        self.button_variants: dict[tk.Label, str] = {}
        self.button_commands: dict[tk.Label, object] = {}
        self.button_enabled: dict[tk.Label, bool] = {}
        self.button_hovering: set[tk.Label] = set()
        self.preview_source_image: Image.Image | None = None
        self.pdf_preview_source_image: Image.Image | None = None
        self.preview_notice = "正在读取剪切板..."
        self.pdf_preview_notice = "正在读取剪切板..."
        self.document_text = ""
        self.manual_layout_params = LayoutParameters()
        self.target_page_count = DEFAULT_START_PAGE_COUNT
        self.initial_target_page_count = DEFAULT_START_PAGE_COUNT
        self.normalized_document_text = ""
        self.base_font_size: float | None = None
        self.base_preferences: FontPreferences | None = None
        self.base_layout_params = LayoutParameters()
        self.preview_overflow = False
        self.current_preview_layout = None
        self.last_preview_pdf_path: Path | None = None
        self.last_preview_pdf_ready = False
        self.preview_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

        self.ui_font_family = tkfont.nametofont("TkDefaultFont").cget("family")
        self.editor_font = tkfont.Font(
            root=self.root,
            family=self._pick_editor_font_family(),
            size=14,
        )
        self.heading_font_family = self._pick_heading_font_family()

        self.page_usage_var = tk.StringVar(value="-")
        self.font_size_var = tk.StringVar(value="-")
        self.margin_var = tk.StringVar(value="侧0 / 上下0 pt")
        self.source_path_var = tk.StringVar(value="-")
        self.output_path_var = tk.StringVar(value="-")
        self.status_var = tk.StringVar(value="正在读取剪切板...")
        self.preview_page_var = tk.StringVar(value="预览：-")
        self.target_page_var = tk.StringVar(value=f"{self.target_page_count} 页")
        self.imposition_enabled_var = tk.BooleanVar(value=False)
        self.print_mode_var = tk.StringVar(value=A4_DUPLEX_LABEL)
        self.layout_control_vars: dict[str, tk.StringVar] = {
            name: tk.StringVar(value="-")
            for name, *_rest in LAYOUT_CONTROL_DEFS
        }
        self.layout_adjust_buttons: list[tk.Label] = []

        self.text_widget: tk.Text | None = None
        self.preview_canvas: tk.Canvas | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.pdf_preview_canvas: tk.Canvas | None = None
        self.floating_menu_canvas: tk.Canvas | None = None
        self.floating_menu_photo: ImageTk.PhotoImage | None = None
        self.pdf_preview_image: ImageTk.PhotoImage | None = None
        self.pdf_preview_images: list[ImageTk.PhotoImage] = []
        self.editor_scrollbar: ttk.Scrollbar | None = None
        self.preview_scrollbar: ttk.Scrollbar | None = None
        self.editor_scrollbar_after_id: str | None = None
        self.preview_scrollbar_after_id: str | None = None
        self.auto_fit_after_id: str | None = None
        self.last_enter_press_at = 0.0
        self.editor_hovering = False
        self.preview_hovering = False
        self.fit_button: tk.Label | None = None
        self.build_print_button: tk.Label | None = None
        self.preview_source_button: tk.Label | None = None
        self.preview_output_button: tk.Label | None = None
        self.print_button: tk.Label | None = None
        self.direct_print_button: tk.Label | None = None
        self.open_output_button: tk.Label | None = None
        self.clear_button: tk.Label | None = None
        self.reset_button: tk.Label | None = None
        self.pdf_preview_card: tk.Frame | None = None
        self.sidebar_card: tk.Frame | None = None
        self.shell_ref: tk.Frame | None = None
        self._settings_panel_visible = False
        self._settings_panel_animating = False
        self._settings_panel_after_id: str | None = None
        self._settings_panel_width = 360
        self._last_floating_menu_click_at = 0.0
        self._last_print_mode = PAGE_MODE_A4
        self.preview_source_images: list[Image.Image] = []

        self._build_ui()
        self._sync_layout_control_vars()
        self._set_pdf_preview_notice(self.pdf_preview_notice)
        self._update_button_states()
        if self.pdf_preview_canvas is not None:
            self.pdf_preview_canvas.focus_set()
        self.root.bind("<Return>", self._handle_paste_page_enter_key)
        self.root.bind("<KP_Enter>", self._handle_paste_page_enter_key)
        self.root.bind("<F5>", self._handle_refresh_shortcut)
        self.root.bind("<<Paste>>", self._handle_paste_page_paste)
        self.root.bind("<Control-v>", self._handle_paste_page_paste)
        self.root.bind("<Control-V>", self._handle_paste_page_paste)
        self.root.bind("<Shift-Insert>", self._handle_paste_page_paste)
        self.root.bind("<Escape>", self._handle_exit_shortcut)
        self.root.bind(
            "<ButtonRelease-1>",
            self._handle_global_pointer_release,
            add="+",
        )
        self.root.after(AUTO_CLIPBOARD_LOAD_DELAY_MS, self._load_clipboard_on_launch)

    def _maximize_window(self) -> None:
        """Start the application in a maximized fullscreen-like window."""

        try:
            self.root.attributes("-fullscreen", True)
            return
        except tk.TclError:
            pass

        try:
            self.root.state("zoomed")
            return
        except tk.TclError:
            pass

        try:
            self.root.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

    def _handle_exit_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Close the settings panel first; otherwise close the application."""

        if self._settings_panel_is_open():
            self._hide_settings_panel()
            return "break"
        self.root.destroy()
        return "break"

    def _handle_paste_page_enter_key(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Only double Enter prints; single Enter no longer triggers preview output."""

        if not self.normalized_document_text or self.base_font_size is None or self.base_preferences is None:
            return "break"

        now = monotonic()
        if now - self.last_enter_press_at <= 0.45:
            self.last_enter_press_at = 0.0
            if not self.print_pdf_ready:
                self.build_print_pdf(open_after_build=False)
            if self.print_pdf_ready:
                self.direct_print_imposed_pdf(show_success_message=True)
        else:
            self.last_enter_press_at = now
        return "break"

    def _handle_select_all(self, _event: tk.Event[tk.Misc]) -> str:
        """Select the entire editor contents."""

        if self.text_widget is None:
            return "break"
        self.text_widget.tag_add("sel", "1.0", "end-1c")
        self.text_widget.mark_set("insert", "1.0")
        self.text_widget.see("insert")
        return "break"

    def _handle_paste_page_keypress(self, event: tk.Event[tk.Misc]) -> str | None:
        """Block free typing on the paste page while still allowing shortcuts and double Enter."""

        keysym = str(getattr(event, "keysym", ""))
        if keysym in {"Return", "KP_Enter"}:
            return self._handle_paste_page_enter_key(event)

        control_pressed = bool(getattr(event, "state", 0) & 0x4)
        lowered = keysym.lower()
        if control_pressed and lowered in {"v", "a", "c", "insert"}:
            return None
        return "break"

    def _handle_paste_page_paste(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        """Refresh the workflow from the current clipboard contents."""

        self._load_clipboard_content(show_messagebox_on_error=True)
        return "break"

    def _handle_refresh_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Reload clipboard content and rerun the validation/build flow."""

        self._load_clipboard_content(show_messagebox_on_error=True)
        return "break"

    def _handle_editor_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        """Keep the editor scroll responsive to the mouse wheel on common platforms."""

        if self.text_widget is None:
            return "break"

        self._show_scrollbar_temporarily("editor")

        if getattr(event, "num", None) == 4:
            self.text_widget.yview_scroll(-3, "units")
            return "break"
        if getattr(event, "num", None) == 5:
            self.text_widget.yview_scroll(3, "units")
            return "break"

        delta = getattr(event, "delta", 0)
        if delta:
            step = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            self.text_widget.yview_scroll(step * 3, "units")
        return "break"

    def _set_editor_hover(self, hovering: bool) -> None:
        """Show the editor scrollbar while the pointer is over the editor area."""

        self.editor_hovering = hovering
        if hovering:
            self._show_scrollbar_temporarily("editor", keep_visible=True)
        else:
            self._schedule_scrollbar_hide("editor")

    def _handle_preview_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        """Keep the preview canvas scroll responsive to the mouse wheel."""

        canvas = self.pdf_preview_canvas or self.preview_canvas
        if canvas is None:
            return "break"

        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-3, "units")
            self._draw_floating_menu()
            return "break"
        if getattr(event, "num", None) == 5:
            canvas.yview_scroll(3, "units")
            self._draw_floating_menu()
            return "break"

        delta = getattr(event, "delta", 0)
        if delta:
            step = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            canvas.yview_scroll(step * 3, "units")
            self._draw_floating_menu()
        return "break"

    def _set_preview_hover(self, hovering: bool) -> None:
        """Show the preview scrollbar while the pointer is over the preview area."""

        self.preview_hovering = hovering
        if hovering:
            self._show_scrollbar_temporarily("preview", keep_visible=True)
        else:
            self._schedule_scrollbar_hide("preview")

    def _update_editor_scrollbar(self, first: str, last: str) -> None:
        """Update editor scrollbar visibility and thumb."""

        if self.editor_scrollbar is None:
            return
        self.editor_scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.editor_scrollbar.place_forget()
            return
        self._show_scrollbar_temporarily("editor")

    def _update_preview_scrollbar(self, first: str, last: str) -> None:
        """Update preview scrollbar visibility and thumb."""

        if self.preview_scrollbar is None:
            return
        self.preview_scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.preview_scrollbar.place_forget()
            return
        self._show_scrollbar_temporarily("preview")

    def _show_scrollbar_temporarily(self, target: str, keep_visible: bool = False) -> None:
        """Reveal a scrollbar briefly while the user is scrolling."""

        if target == "editor":
            scrollbar = self.editor_scrollbar
            after_id = self.editor_scrollbar_after_id
        else:
            scrollbar = self.preview_scrollbar
            after_id = self.preview_scrollbar_after_id

        if scrollbar is None:
            return

        if target == "editor":
            scrollbar.place(relx=1.0, x=-16, y=18, width=8, relheight=1.0, height=-36)
        else:
            scrollbar.place(relx=1.0, x=-16, y=18, width=8, relheight=1.0, height=-36)
        if after_id is not None:
            self.root.after_cancel(after_id)

        if keep_visible:
            if target == "editor":
                self.editor_scrollbar_after_id = None
            else:
                self.preview_scrollbar_after_id = None
            return

        self._schedule_scrollbar_hide(target)

    def _schedule_scrollbar_hide(self, target: str) -> None:
        """Hide the given scrollbar after a short delay unless the pointer is still over it."""

        if target == "editor":
            if self.editor_scrollbar is None:
                return
            if self.editor_scrollbar_after_id is not None:
                self.root.after_cancel(self.editor_scrollbar_after_id)
            self.editor_scrollbar_after_id = self.root.after(900, lambda: self._hide_scrollbar("editor"))
        else:
            if self.preview_scrollbar is None:
                return
            if self.preview_scrollbar_after_id is not None:
                self.root.after_cancel(self.preview_scrollbar_after_id)
            self.preview_scrollbar_after_id = self.root.after(900, lambda: self._hide_scrollbar("preview"))

    def _hide_scrollbar(self, target: str) -> None:
        """Hide the given scrollbar after the short reveal window expires."""

        if target == "editor":
            scrollbar = self.editor_scrollbar
            self.editor_scrollbar_after_id = None
            if self.editor_hovering:
                return
        else:
            scrollbar = self.preview_scrollbar
            self.preview_scrollbar_after_id = None
            if self.preview_hovering:
                return

        if scrollbar is not None:
            scrollbar.place_forget()

    def _cancel_auto_fit(self) -> None:
        """Cancel any pending debounced auto-fit operation."""

        if self.auto_fit_after_id is not None:
            self.root.after_cancel(self.auto_fit_after_id)
            self.auto_fit_after_id = None

    def _schedule_auto_fit(self) -> None:
        """Debounce auto-fit so typing pauses for a moment before rebuilding."""

        self._cancel_auto_fit()
        self.auto_fit_after_id = self.root.after(1000, self._run_auto_fit)

    def _run_auto_fit(self) -> None:
        """Execute the pending auto-fit build."""

        self.auto_fit_after_id = None
        if not self._get_editor_text().strip():
            return
        self.fit_document_to_pages(show_empty_error=False, show_messagebox_on_error=False)

    def _reset_generated_state(self) -> None:
        """Clear generated paths, preview, and status back to the empty state."""

        self._cancel_auto_fit()
        self.result = None
        self.source_path = None
        self.print_source_path = None
        self.output_path = None
        self.print_pdf_ready = False
        self.normalized_document_text = ""
        self.base_font_size = None
        self.base_preferences = None
        self.base_layout_params = LayoutParameters()
        self.initial_target_page_count = DEFAULT_START_PAGE_COUNT
        self.preview_overflow = False
        self.current_preview_layout = None
        self.last_preview_pdf_path = None
        self.last_preview_pdf_ready = False
        self.pdf_preview_source_image = None
        self.preview_source_images = []
        self.pdf_preview_images = []
        self.page_usage_var.set("-")
        self.font_size_var.set("-")
        self.margin_var.set("侧0 / 上下0 pt")
        self.source_path_var.set("-")
        self.output_path_var.set("-")
        self.preview_page_var.set("预览：-")
        self._set_preview_notice("等待剪切板内容")
        self._set_pdf_preview_notice("等待剪切板内容\n复制文本后按 Ctrl+V 或 F5 读取")
        self._set_overflow_visual_state(False)

    def _current_font_preferences(self) -> FontPreferences:
        """Return the default mixed-script sizing preferences."""

        return FontPreferences(latin_scale=1.0, cjk_scale=0.7)

    def _record_current_font_size_history(self) -> None:
        """Remember the current printed base font size for future searches."""

        if self.result is None:
            return
        record_font_size_history(self.result.font_size)

    def _pick_editor_font_family(self) -> str:
        """Choose a UI font family that can display Chinese text on common desktops."""

        available_families = set(tkfont.families(self.root))
        default_family = tkfont.nametofont("TkDefaultFont").cget("family")
        preferred = (
            "Avenir Next",
            "Segoe UI Variable",
            "Noto Sans CJK SC",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "PingFang SC",
            "Source Han Sans SC",
            default_family,
            "Noto Sans SC",
            "Ubuntu",
            "Helvetica Neue",
            "WenQuanYi Zen Hei",
            "SimSun",
        )
        for family in preferred:
            if family in available_families:
                return family
        return default_family

    def _pick_heading_font_family(self) -> str:
        """Pick a heading font closer to the reader style from project 14."""

        available_families = set(tkfont.families(self.root))
        preferred = (
            "Iowan Old Style",
            "Palatino Linotype",
            "Book Antiqua",
            "Noto Serif CJK SC",
            "Source Han Serif SC",
            "STSong",
            "SimSun",
            self.editor_font.cget("family"),
        )
        for family in preferred:
            if family in available_families:
                return family
        return self.editor_font.cget("family")

    def _create_card(
        self,
        parent: tk.Misc,
        *,
        bg: str,
        padx: int = 0,
        pady: int = 0,
        border: bool = True,
    ) -> tk.Frame:
        """Create a bordered dark surface card."""

        return tk.Frame(
            parent,
            bg=bg,
            padx=padx,
            pady=pady,
            bd=0,
            highlightthickness=1 if border else 0,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["border"],
        )

    def _create_action_button(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command: object,
        variant: str = "ghost",
    ) -> tk.Label:
        """Create a palette-controlled action button.

        macOS Aqua can ignore ``bg`` on a native ``tk.Button``.  A label with
        explicit mouse bindings keeps the same action semantics while making
        the dark/primary palette deterministic.
        """

        button = tk.Label(
            parent,
            text=text,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=14,
            pady=8,
            font=(self.ui_font_family, 11, "bold"),
            highlightthickness=0,
            anchor=tk.CENTER,
            justify=tk.CENTER,
        )
        self.button_variants[button] = variant
        self.button_commands[button] = command
        self.button_enabled[button] = True
        button.bind(
            "<Button-1>",
            lambda _event, target=button: self._invoke_action_button(target),
        )
        button.bind(
            "<Enter>",
            lambda _event, target=button: self._set_action_button_hover(target, True),
        )
        button.bind(
            "<Leave>",
            lambda _event, target=button: self._set_action_button_hover(target, False),
        )
        self._set_button_enabled(button, True)
        return button

    def _invoke_action_button(self, button: tk.Label) -> str:
        """Invoke a custom action button unless it is disabled."""

        if not self.button_enabled.get(button, False):
            return "break"
        command = self.button_commands.get(button)
        if callable(command):
            command()
        return "break"

    def _set_action_button_hover(self, button: tk.Label, hovering: bool) -> None:
        """Apply the hover palette to one custom action button."""

        if hovering:
            self.button_hovering.add(button)
        else:
            self.button_hovering.discard(button)
        self._set_button_enabled(button, self.button_enabled.get(button, False))

    def _set_button_enabled(self, button: tk.Label, enabled: bool) -> None:
        """Apply palette and disabled state to an action button."""

        self.button_enabled[button] = enabled
        variant = self.button_variants.get(button, "ghost")

        if not enabled:
            bg = THEME["disabled_bg"]
            fg = THEME["disabled_fg"]
            cursor = "arrow"
        else:
            if variant == "primary":
                bg = THEME["accent"]
                fg = THEME["shell"]
                active_bg = THEME["accent_strong"]
                active_fg = THEME["shell"]
            elif variant == "danger":
                bg = THEME["button"]
                fg = THEME["danger"]
                active_bg = THEME["button_hover"]
                active_fg = THEME["danger"]
            else:
                bg = THEME["button"]
                fg = THEME["ink"]
                active_bg = THEME["button_hover"]
                active_fg = THEME["ink"]

            if button in self.button_hovering:
                bg = active_bg
                fg = active_fg
            cursor = "hand2"

        button.configure(
            state=tk.NORMAL if enabled else tk.DISABLED,
            bg=bg,
            fg=fg,
            cursor=cursor,
        )

    def _format_layout_param_value(self, name: str, value: float) -> str:
        """Return a compact label for one manual layout control."""

        for candidate_name, _label, _minimum, _maximum, _step, template in LAYOUT_CONTROL_DEFS:
            if candidate_name == name:
                return template.format(value)
        return f"{value:.2f}"

    def _sync_layout_control_vars(self) -> None:
        """Mirror the current manual layout settings into the sidebar labels."""

        self.print_mode_var.set("拼板" if self._is_cutstack_mode() else A4_DUPLEX_LABEL)
        self.target_page_var.set(f"{self.target_page_count} 页")
        for name, *_rest in LAYOUT_CONTROL_DEFS:
            value = getattr(self.manual_layout_params, name)
            self.layout_control_vars[name].set(self._format_layout_param_value(name, value))

    def _is_cutstack_mode(self) -> bool:
        """Return whether the final print PDF should be 2x2 imposed."""

        return bool(self.imposition_enabled_var.get())

    def _current_page_mode(self) -> str:
        """Return the page-fitting mode for the current print switch."""

        return PAGE_MODE_CUTSTACK if self._is_cutstack_mode() else PAGE_MODE_A4

    def _current_print_hint(self) -> str:
        """Return the print dialog hint for the current output mode."""

        return CUTSTACK_PRINT_HINT if self._is_cutstack_mode() else A4_PRINT_HINT

    def _current_page_dimensions(self) -> tuple[float, float]:
        """Return preview/render dimensions for the selected output mode."""

        return get_page_dimensions(self._current_page_mode())

    def _normalize_current_target_page_count(self) -> bool:
        """Normalize the target page count for the selected mode."""

        normalized = normalize_target_page_count(self.target_page_count, page_mode=self._current_page_mode())
        if normalized == self.target_page_count:
            return False
        self.target_page_count = normalized
        return True

    def _handle_print_mode_toggle(self) -> None:
        """Switch between imposed booklet output and normal full-page A4 output."""

        next_mode = self._current_page_mode()
        previous_mode = self._last_print_mode
        if next_mode != previous_mode:
            if next_mode == PAGE_MODE_CUTSTACK:
                # One A4 page becomes four A6 cut pages in imposed mode.
                self.target_page_count = normalize_target_page_count(
                    self.target_page_count * 4,
                    page_mode=PAGE_MODE_CUTSTACK,
                )
            else:
                # Returning to normal A4 keeps the same amount of content,
                # rather than leaving the old 8-page cut-stack target in place.
                self.target_page_count = normalize_target_page_count(
                    max(get_min_target_page_count(PAGE_MODE_A4), self.target_page_count // 4),
                    page_mode=PAGE_MODE_A4,
                )
            self._last_print_mode = next_mode
        else:
            self._normalize_current_target_page_count()

        # The settings card is an overlay, not part of the PDF state.  Close it
        # synchronously on a mode change so a partially completed slide cannot
        # leave a narrow strip of the old menu over the new preview.
        self._hide_settings_panel(immediate=True)
        self._sync_layout_control_vars()
        self._rerun_search_after_structure_change("已切换打印模式，正在重新搜索排版...")

    def _rerun_search_after_structure_change(self, status_message: str) -> None:
        """Re-run the full fitter when page groups or output format change."""

        self.output_path = None
        self.output_path_var.set("-")
        self.print_pdf_ready = False
        self.last_preview_pdf_ready = False
        self.last_preview_pdf_path = None
        self.status_var.set(status_message)
        if self._get_editor_text().strip():
            self.fit_document_to_pages(show_empty_error=False, show_messagebox_on_error=False)
        else:
            self._set_preview_notice("等待剪切板内容")
            self._set_pdf_preview_notice("等待剪切板内容\n复制文本后按 Ctrl+V 或 F5 读取")
            self._update_button_states()

    def _refresh_preview_after_parameter_change(self) -> None:
        """Rebuild the last-page source preview after a page-count or layout change."""

        self.output_path = None
        self.output_path_var.set("-")
        self.print_pdf_ready = False
        self.last_preview_pdf_ready = False
        self.last_preview_pdf_path = None
        if self.normalized_document_text and self.base_font_size is not None and self.base_preferences is not None:
            self._render_preview_from_fixed_search(show_messagebox_on_error=False)
        else:
            self.status_var.set("参数已更新，等待剪切板内容。")
            self._update_button_states()

    def _set_overflow_visual_state(self, overflow: bool) -> None:
        """Mark only the left preview area red when content spills beyond the last page."""

        self.preview_overflow = overflow
        border_color = THEME["danger"] if overflow else THEME["border"]
        canvas_bg = THEME["danger_surface_strong"] if overflow else THEME["panel"]

        if self.pdf_preview_card is not None:
            self.pdf_preview_card.configure(highlightbackground=border_color, highlightcolor=border_color)
        if self.pdf_preview_canvas is not None:
            self.pdf_preview_canvas.configure(bg=canvas_bg)

    def _adjust_target_page_count(self, delta_pages: int) -> None:
        """Adjust the target page count in the selected mode's page-count steps."""

        step = get_target_page_step(self._current_page_mode())
        delta = step if delta_pages > 0 else -step
        next_value = max(
            get_min_target_page_count(self._current_page_mode()),
            min(MAX_TARGET_PAGE_COUNT, self.target_page_count + delta),
        )
        next_value = normalize_target_page_count(next_value, page_mode=self._current_page_mode())
        if next_value == self.target_page_count:
            return
        self.target_page_count = next_value
        self._sync_layout_control_vars()
        self._rerun_search_after_structure_change("页数已调整，正在重新搜索排版...")

    def _adjust_layout_param(self, name: str, delta: float) -> None:
        """Apply one manual layout adjustment, then refresh the imposed preview."""

        for candidate_name, _label, minimum, maximum, _step, _template in LAYOUT_CONTROL_DEFS:
            if candidate_name != name:
                continue
            current_value = getattr(self.manual_layout_params, name)
            next_value = max(minimum, min(maximum, round(current_value + delta, 4)))
            next_params = replace(self.manual_layout_params, **{name: next_value})
            safe_params = get_print_safe_layout_parameters(next_params, self._current_page_mode())
            if safe_params == self.manual_layout_params:
                return
            self.manual_layout_params = safe_params
            self._sync_layout_control_vars()
            self._refresh_preview_after_parameter_change()
            return

    def _create_info_row(self, parent: tk.Misc, label: str, variable: tk.StringVar) -> None:
        """Create a compact two-line info block in the sidebar."""

        row = tk.Frame(parent, bg=THEME["panel"])
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            row,
            text=label,
            bg=THEME["panel"],
            fg=THEME["muted"],
            font=(self.ui_font_family, 10),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            row,
            textvariable=variable,
            bg=THEME["panel"],
            fg=THEME["ink"],
            font=(self.ui_font_family, 11, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=280,
        ).pack(fill=tk.X, pady=(2, 0))

    def _build_ui(self) -> None:
        """Create a PDF-first workspace with a project-14-style settings overlay."""

        shell = tk.Frame(self.root, bg=THEME["shell"], padx=10, pady=10)
        shell.pack(fill=tk.BOTH, expand=True)
        self.shell_ref = shell
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        self.text_widget = None
        self.editor_scrollbar = None

        preview_stage = tk.Frame(shell, bg=THEME["shell"])
        preview_stage.grid(row=0, column=0, sticky="nsew")
        preview_stage.grid_columnconfigure(0, weight=1)
        preview_stage.grid_rowconfigure(0, weight=1)

        pdf_preview_card = self._create_card(preview_stage, bg=THEME["panel"])
        pdf_preview_card.grid(row=0, column=0, sticky="nsew")
        pdf_preview_card.grid_columnconfigure(0, weight=1)
        pdf_preview_card.grid_rowconfigure(0, weight=1)
        self.pdf_preview_card = pdf_preview_card

        self.pdf_preview_canvas = tk.Canvas(
            pdf_preview_card,
            bg=THEME["panel"],
            highlightthickness=0,
            bd=0,
            takefocus=1,
            relief=tk.FLAT,
        )
        self.pdf_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.pdf_preview_canvas.bind("<Configure>", self._handle_pdf_preview_resize)
        self.pdf_preview_canvas.bind("<MouseWheel>", self._handle_preview_mousewheel)
        self.pdf_preview_canvas.bind("<Button-4>", self._handle_preview_mousewheel)
        self.pdf_preview_canvas.bind("<Button-5>", self._handle_preview_mousewheel)
        self.pdf_preview_canvas.bind("<Escape>", self._handle_exit_shortcut)
        # Keep the floating control inside the same Canvas as the PDF.  A child
        # Frame/Canvas would paint a rectangular background over the page; a
        # transparent PNG Canvas item lets the PDF remain visible around and
        # inside the icon, matching Project 14's overlay behavior.
        self.pdf_preview_canvas.tag_bind(
            "floating_menu",
            "<Button-1>",
            self._handle_floating_menu_click,
        )
        self.pdf_preview_canvas.tag_bind(
            "floating_menu",
            "<ButtonRelease-1>",
            self._handle_floating_menu_click,
        )
        self.pdf_preview_canvas.tag_bind(
            "floating_menu",
            "<Enter>",
            lambda _event: self.pdf_preview_canvas.configure(cursor="hand2"),
        )
        self.pdf_preview_canvas.tag_bind(
            "floating_menu",
            "<Leave>",
            lambda _event: self.pdf_preview_canvas.configure(cursor="arrow"),
        )
        self.floating_menu_canvas = self.pdf_preview_canvas
        self.floating_menu_photo = self._load_floating_menu_photo()
        self.preview_canvas = None

        sidebar = self._create_card(shell, bg=THEME["panel_strong"], padx=14, pady=14)
        sidebar.configure(width=self._settings_panel_width)
        sidebar.place_forget()
        self.sidebar_card = sidebar

        settings_header = tk.Frame(sidebar, bg=THEME["panel_strong"])
        settings_header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            settings_header,
            text="排版参数",
            bg=THEME["panel_strong"],
            fg=THEME["ink"],
            font=(self.heading_font_family, 16, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT)
        close_settings = tk.Label(
            settings_header,
            text="×",
            bg=THEME["panel_strong"],
            fg=THEME["muted"],
            cursor="hand2",
            font=(self.ui_font_family, 18),
        )
        close_settings.pack(side=tk.RIGHT, padx=(8, 0))
        close_settings.bind("<Button-1>", lambda _event: self._hide_settings_panel())
        close_settings.bind(
            "<Enter>",
            lambda _event: close_settings.configure(fg=THEME["danger"]),
        )
        close_settings.bind(
            "<Leave>",
            lambda _event: close_settings.configure(fg=THEME["muted"]),
        )

        mode_row = tk.Frame(sidebar, bg=THEME["panel_strong"])
        mode_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            mode_row,
            text="打印模式",
            bg=THEME["panel_strong"],
            fg=THEME["muted"],
            font=(self.ui_font_family, 10),
            anchor="w",
            width=9,
        ).pack(side=tk.LEFT)
        mode_switch = tk.Checkbutton(
            mode_row,
            text="拼板",
            variable=self.imposition_enabled_var,
            command=self._handle_print_mode_toggle,
            bg=THEME["panel_strong"],
            fg=THEME["ink"],
            activebackground=THEME["panel_strong"],
            activeforeground=THEME["accent"],
            selectcolor=THEME["button"],
            cursor="hand2",
            font=(self.ui_font_family, 10, "bold"),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
        )
        mode_switch.pack(side=tk.LEFT)
        tk.Label(
            mode_row,
            textvariable=self.print_mode_var,
            bg=THEME["panel_strong"],
            fg=THEME["accent"],
            font=(self.ui_font_family, 10, "bold"),
            anchor="e",
        ).pack(side=tk.RIGHT)

        controls = tk.Frame(sidebar, bg=THEME["panel_strong"])
        controls.pack(fill=tk.BOTH, expand=True)

        page_row = tk.Frame(controls, bg=THEME["panel_strong"])
        page_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            page_row,
            text="页数",
            bg=THEME["panel_strong"],
            fg=THEME["muted"],
            font=(self.ui_font_family, 10),
            anchor="w",
            width=9,
        ).pack(side=tk.LEFT)
        page_minus_button = self._create_action_button(
            page_row,
            text="-",
            command=lambda: self._adjust_target_page_count(-TARGET_PAGE_STEP),
        )
        page_minus_button.configure(font=(self.ui_font_family, 10, "bold"), padx=10, pady=4)
        page_minus_button.pack(side=tk.LEFT)
        self.layout_adjust_buttons.append(page_minus_button)
        tk.Label(
            page_row,
            textvariable=self.target_page_var,
            bg=THEME["panel_strong"],
            fg=THEME["ink"],
            font=(self.ui_font_family, 10, "bold"),
            anchor="center",
            width=10,
        ).pack(side=tk.LEFT, padx=8)
        page_plus_button = self._create_action_button(
            page_row,
            text="+",
            command=lambda: self._adjust_target_page_count(TARGET_PAGE_STEP),
        )
        page_plus_button.configure(font=(self.ui_font_family, 10, "bold"), padx=10, pady=4)
        page_plus_button.pack(side=tk.LEFT)
        self.layout_adjust_buttons.append(page_plus_button)

        for name, label, _minimum, _maximum, step, _template in LAYOUT_CONTROL_DEFS:
            row = tk.Frame(controls, bg=THEME["panel_strong"])
            row.pack(fill=tk.X, pady=(0, 8))
            tk.Label(
                row,
                text=label,
                bg=THEME["panel_strong"],
                fg=THEME["muted"],
                font=(self.ui_font_family, 10),
                anchor="w",
                width=9,
            ).pack(side=tk.LEFT)
            minus_button = self._create_action_button(
                row,
                text="-",
                command=lambda key=name, step_value=step: self._adjust_layout_param(key, -step_value),
            )
            minus_button.configure(font=(self.ui_font_family, 10, "bold"), padx=10, pady=4)
            minus_button.pack(side=tk.LEFT)
            self.layout_adjust_buttons.append(minus_button)
            tk.Label(
                row,
                textvariable=self.layout_control_vars[name],
                bg=THEME["panel_strong"],
                fg=THEME["ink"],
                font=(self.ui_font_family, 10, "bold"),
                anchor="center",
                width=10,
            ).pack(side=tk.LEFT, padx=8)
            plus_button = self._create_action_button(
                row,
                text="+",
                command=lambda key=name, step_value=step: self._adjust_layout_param(key, step_value),
            )
            plus_button.configure(font=(self.ui_font_family, 10, "bold"), padx=10, pady=4)
            plus_button.pack(side=tk.LEFT)
            self.layout_adjust_buttons.append(plus_button)

        self.reset_button = self._create_action_button(
            sidebar,
            text="重置为初始搜索结果",
            command=self.reset_layout_to_initial_search,
            variant="primary",
        )
        self.reset_button.pack(fill=tk.X, pady=(10, 0))

    def _settings_panel_is_open(self) -> bool:
        """Return whether the settings card is currently visible over the preview."""

        return self._settings_panel_visible

    def _handle_floating_menu_click(self, _event: tk.Event[tk.Misc]) -> str:
        """Toggle the right-side settings card from the floating hamburger icon."""

        now = monotonic()
        if now - self._last_floating_menu_click_at < 0.15:
            return "break"
        self._last_floating_menu_click_at = now
        if self._settings_panel_is_open():
            self._hide_settings_panel()
        else:
            self._show_settings_panel()
        return "break"

    def _handle_global_pointer_release(self, event: tk.Event[tk.Misc]) -> str | None:
        """Keep the floating menu clickable across Tk/macOS Retina coordinate scaling."""

        canvas = self.pdf_preview_canvas
        if canvas is None or not canvas.winfo_exists():
            return None
        try:
            local_x = event.x_root - canvas.winfo_rootx()
            local_y = event.y_root - canvas.winfo_rooty()
            canvas_x = canvas.canvasx(local_x)
            canvas_y = canvas.canvasy(local_y)
            hit_items = canvas.find_overlapping(
                canvas_x - 1,
                canvas_y - 1,
                canvas_x + 1,
                canvas_y + 1,
            )
            if any("floating_menu" in canvas.gettags(item_id) for item_id in hit_items):
                return self._handle_floating_menu_click(event)
        except tk.TclError:
            pass
        return None

    def _show_settings_panel(self) -> None:
        """Slide the existing layout controls over the preview from the right."""

        panel = self.sidebar_card
        shell = self.shell_ref
        if panel is None or shell is None or not panel.winfo_exists():
            return
        if self._settings_panel_animating or self._settings_panel_is_open():
            return

        self._settings_panel_visible = True
        shell.update_idletasks()
        shell_width = max(shell.winfo_width(), self.root.winfo_width(), 720)
        panel_width = min(380, max(340, shell_width // 2))
        self._settings_panel_width = panel_width
        panel.configure(width=panel_width)
        panel.place(
            relx=1.0,
            rely=0.0,
            relheight=1.0,
            anchor="ne",
            width=panel_width,
            x=panel_width,
        )
        panel.lift()

        steps = 8
        step_ms = 18

        def animate(step: int) -> None:
            if not panel.winfo_exists():
                self._settings_panel_animating = False
                self._settings_panel_after_id = None
                return
            progress = step / steps
            eased = 1.0 - (1.0 - progress) ** 2
            panel.place_configure(x=int(panel_width * (1.0 - eased)))
            if step < steps:
                self._settings_panel_after_id = panel.after(
                    step_ms,
                    lambda next_step=step + 1: animate(next_step),
                )
            else:
                self._settings_panel_after_id = None
                self._settings_panel_animating = False
                self._draw_floating_menu()

        self._settings_panel_animating = True
        animate(0)

    def _hide_settings_panel(self, *, immediate: bool = False) -> None:
        """Slide the settings card out and return the preview to its uncluttered state."""

        panel = self.sidebar_card
        if panel is None or not panel.winfo_exists():
            return
        if not self._settings_panel_is_open() and not self._settings_panel_animating:
            return

        if immediate:
            if self._settings_panel_after_id is not None:
                try:
                    panel.after_cancel(self._settings_panel_after_id)
                except tk.TclError:
                    pass
                self._settings_panel_after_id = None
            panel.place_forget()
            self._settings_panel_visible = False
            self._settings_panel_animating = False
            self._draw_floating_menu()
            return

        if self._settings_panel_after_id is not None:
            try:
                panel.after_cancel(self._settings_panel_after_id)
            except tk.TclError:
                pass
            self._settings_panel_after_id = None

        panel_width = max(panel.winfo_width(), self._settings_panel_width, 340)
        steps = 6
        step_ms = 16

        def animate(step: int) -> None:
            if not panel.winfo_exists():
                self._settings_panel_animating = False
                self._settings_panel_after_id = None
                return
            progress = (step + 1) / steps
            panel.place_configure(x=int(panel_width * progress))
            if step < steps - 1:
                self._settings_panel_after_id = panel.after(
                    step_ms,
                    lambda next_step=step + 1: animate(next_step),
                )
            else:
                self._settings_panel_after_id = None
                panel.place_forget()
                self._settings_panel_visible = False
                self._settings_panel_animating = False
                self._draw_floating_menu()

        self._settings_panel_animating = True
        animate(0)

    def clear_editor(self) -> None:
        """Clear the paste page and reset generated output."""

        self._set_paste_page_text("")
        self.last_enter_press_at = 0.0
        self.status_var.set("等待剪切板内容")
        self._reset_generated_state()
        self._update_button_states()
        if self.pdf_preview_canvas is not None:
            self.pdf_preview_canvas.focus_set()

    def _set_paste_page_text(self, text: str) -> None:
        """Update the internal document text cache."""

        self.document_text = text

    def _get_editor_text(self) -> str:
        """Return the current document contents."""

        if self.text_widget is not None:
            return self.text_widget.get("1.0", "end-1c")
        return self.document_text

    def _validate_clipboard_text(self, text: str) -> tuple[bool, str]:
        """Require long clipboard content, allowing English-only documents."""

        normalized = text.strip()
        if not normalized:
            return False, "剪贴板为空，未进入排版流程。"

        latin_count = len(re.findall(r"[A-Za-z]", normalized))
        cjk_count = sum(1 for char in normalized if "\u4e00" <= char <= "\u9fff")
        total_chars = len(normalized)

        if total_chars < MIN_VALIDATION_TOTAL_CHARS:
            return False, f"内容不够长：当前 {total_chars} 字，至少需要 {MIN_VALIDATION_TOTAL_CHARS} 字。"
        if latin_count < MIN_VALIDATION_LATIN_CHARS:
            return False, f"英文内容不足：当前 {latin_count} 个字母，至少需要 {MIN_VALIDATION_LATIN_CHARS}。"
        if 0 < cjk_count < MIN_VALIDATION_CJK_CHARS:
            return False, f"含中文时至少需要 {MIN_VALIDATION_CJK_CHARS} 个汉字：当前 {cjk_count}。"
        return True, ""

    def _load_clipboard_on_launch(self) -> None:
        """Import clipboard text once after startup and enter the normal build flow."""

        self.status_var.set("正在读取剪切板...")
        self._set_pdf_preview_notice("正在读取剪切板...")
        self._load_clipboard_content(show_messagebox_on_error=False)

    def _load_clipboard_content(self, *, show_messagebox_on_error: bool) -> None:
        """Load clipboard text, validate it, then continue into the normal build flow."""

        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            message = "未能读取剪贴板内容。"
            self.status_var.set(message)
            self._set_preview_notice(message)
            self._set_pdf_preview_notice(message)
            if show_messagebox_on_error:
                messagebox.showerror("读取失败", message, parent=self.root)
            return

        is_valid, validation_message = self._validate_clipboard_text(clipboard_text)
        if not is_valid:
            self._set_paste_page_text("")
            self._reset_generated_state()
            self.status_var.set(validation_message)
            self._set_preview_notice(
                "剪贴板内容未通过验证。\n\n"
                f"{validation_message}\n\n"
                "要求至少 1800 个字符和 180 个英文字母；如果内容含中文，还需至少 180 个汉字。"
            )
            self._set_pdf_preview_notice(
                "剪贴板内容未通过验证\n\n"
                f"{validation_message}\n\n"
                "请复制符合要求的文本后按 Ctrl+V 或 F5 重试"
            )
            if show_messagebox_on_error:
                messagebox.showwarning("未通过验证", validation_message, parent=self.root)
            return

        self._set_paste_page_text(clipboard_text)
        self.last_enter_press_at = 0.0
        self.status_var.set(f"已读取剪切板：{len(clipboard_text.strip())} 字，正在排版...")
        self._set_preview_notice("已读取剪切板，正在排版...")
        self._set_pdf_preview_notice(f"已读取剪切板：{len(clipboard_text.strip())} 字\n正在搜索排版参数...")
        self.root.update_idletasks()
        self.fit_document_to_pages(show_empty_error=False, show_messagebox_on_error=show_messagebox_on_error)
        if self.pdf_preview_canvas is not None:
            self.pdf_preview_canvas.focus_set()

    def _on_editor_modified(self, _event: tk.Event[tk.Misc] | None) -> None:
        """Mark generated output as stale whenever the editor text changes."""

        if self.text_widget is None or not self.text_widget.edit_modified():
            return

        current_text = self._get_editor_text()
        if current_text.strip():
            self.status_var.set("内容已修改，停止输入 1 秒后自动刷新预览。")
            self._schedule_auto_fit()
        else:
            self.status_var.set("请先输入或粘贴文档内容。")
            self._reset_generated_state()
        self.is_dirty = True
        self._update_button_states()
        self.text_widget.edit_modified(False)

    def _update_button_states(self) -> None:
        """Enable output actions only when the latest generated files are up to date."""

        has_text = bool(self._get_editor_text().strip())
        if self.reset_button is not None:
            self._set_button_enabled(self.reset_button, has_text and self.base_font_size is not None)

    def _set_preview_notice(self, message: str) -> None:
        """Show a placeholder or error message in the preview pane."""

        self.preview_notice = message
        self.preview_source_image = None
        self.preview_source_images = []
        self.preview_image = None
        self.preview_page_var.set("预览：-")
        self._render_preview_canvas()

    def _set_pdf_preview_notice(self, message: str) -> None:
        """Show a placeholder or error message in the PDF preview pane."""

        self.pdf_preview_notice = message
        self.pdf_preview_source_image = None
        self.preview_source_images = []
        self.pdf_preview_image = None
        self.pdf_preview_images = []
        self._render_pdf_preview_canvas()

    def _handle_preview_resize(self, _event: tk.Event[tk.Misc]) -> None:
        """Keep the preview centered and scaled with the canvas size."""

        self._render_preview_canvas()

    def _handle_pdf_preview_resize(self, _event: tk.Event[tk.Misc]) -> None:
        """Keep the PDF preview centered and scaled with the canvas size."""

        self._render_pdf_preview_canvas()

    def _build_preview_page_image(self, image: Image.Image) -> Image.Image:
        """Decorate the last-page preview so overflow is visually obvious."""

        base = image.convert("RGBA")
        if not self.preview_overflow:
            return base.convert("RGB")

        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        danger_rgb = tuple(int(THEME["danger"].lstrip("#")[index:index + 2], 16) for index in (0, 2, 4))
        border_width = max(6, base.width // 120)
        draw.rectangle(
            (
                border_width // 2,
                border_width // 2,
                base.width - border_width // 2 - 1,
                base.height - border_width // 2 - 1,
            ),
            outline=danger_rgb + (255,),
            width=border_width,
        )
        draw.line(
            (
                border_width,
                base.height - border_width * 2,
                base.width - border_width,
                base.height - border_width * 2,
            ),
            fill=danger_rgb + (255,),
            width=border_width,
        )
        return Image.alpha_composite(base, overlay).convert("RGB")

    def _get_preview_font_resource(self, font_name: str) -> tuple[Path, int]:
        """Resolve the same font files used by the PDF renderer for bitmap preview."""

        candidates = PRIMARY_FONT_CANDIDATES if font_name == PRIMARY_FONT_NAME else FALLBACK_FONT_CANDIDATES
        for font_path in candidates:
            if not font_path.exists():
                continue
            return font_path, get_font_subfont_index(font_path)
        fallback = PRIMARY_FONT_CANDIDATES[0] if font_name == PRIMARY_FONT_NAME else FALLBACK_FONT_CANDIDATES[0]
        return fallback, get_font_subfont_index(fallback)

    def _load_preview_font(self, font_name: str, pixel_size: int) -> ImageFont.FreeTypeFont:
        """Load one preview font with caching so redraw stays responsive."""

        cache_key = (font_name, max(1, pixel_size))
        cached = self.preview_font_cache.get(cache_key)
        if cached is not None:
            return cached

        font_path, font_index = self._get_preview_font_resource(font_name)
        font = ImageFont.truetype(str(font_path), cache_key[1], index=font_index)
        self.preview_font_cache[cache_key] = font
        return font

    def _draw_preview_run(
        self,
        draw: ImageDraw.ImageDraw,
        x: float,
        baseline_y: float,
        run_text: str,
        font: ImageFont.FreeTypeFont,
        *,
        fill: str,
        char_spacing_px: float,
        word_spacing_px: float,
        stroke_width: int = 0,
    ) -> float:
        """Draw one run with explicit char/word spacing so preview matches PDF layout."""

        cursor_x = x
        for index, char in enumerate(run_text):
            draw.text(
                (cursor_x, baseline_y),
                char,
                font=font,
                fill=fill,
                anchor="ls",
                stroke_width=stroke_width,
                stroke_fill=fill,
            )
            advance = draw.textlength(char, font=font)
            if char == " ":
                advance += word_spacing_px
            if index < len(run_text) - 1:
                advance += char_spacing_px
            cursor_x += advance
        return cursor_x

    def _render_layout_page_image(
        self,
        layout,
        *,
        width_px: int,
        height_px: int,
        page_index: int,
    ) -> Image.Image:
        """Render one laid-out source page as a bitmap using the actual PDF font files."""

        image = Image.new("RGB", (width_px, height_px), THEME["page"])
        draw = ImageDraw.Draw(image)

        scale_x = width_px / layout.page_width_pt
        scale_y = height_px / layout.page_height_pt
        scale = min(scale_x, scale_y)
        char_spacing_px = layout.params.char_spacing_pt * scale
        word_spacing_px = layout.params.word_spacing_pt * scale

        boundary_y = height_px - int(layout.params.footer_padding_pt * scale)
        draw.line(
            (8, boundary_y, width_px - 8, boundary_y),
            fill=THEME["danger"] if self.preview_overflow else THEME["border"],
            width=2,
        )

        if page_index >= layout.page_count:
            return image

        page_lines = layout.pages[page_index]
        vertical_center_offset = get_page_vertical_center_offset(layout, page_lines)
        first_line_font_size = get_max_effective_font_size(
            get_wrapped_line_font_size(layout.font_size, page_lines[0]),
            layout.preferences,
        ) if page_lines else get_max_effective_font_size(layout.font_size, layout.preferences)
        baseline_y = (
            layout.params.top_margin_pt
            + vertical_center_offset
            + first_line_font_size
        ) * scale
        x_start = layout.params.side_margin_pt * scale

        for line_index, wrapped_line in enumerate(page_lines):
            line_font_size = get_wrapped_line_font_size(layout.font_size, wrapped_line)
            if line_index > 0 and wrapped_line.paragraph_break_before and layout.params.paragraph_before_gap_pt > 0:
                baseline_y += layout.params.paragraph_before_gap_pt * scale
            cursor_x = x_start + wrapped_line.first_line_indent_pt * scale
            line_char_spacing_px = char_spacing_px
            if wrapped_line.text and wrapped_line.alignment == TEXT_ALIGNMENT_CENTER:
                text_width_px = measure_text_width(
                    wrapped_line.text,
                    line_font_size,
                    layout.preferences,
                    layout.params,
                ) * scale
                cursor_x = (width_px - text_width_px) / 2
            elif wrapped_line.text and not wrapped_line.paragraph_break_after and len(wrapped_line.text) > 1:
                text_width_px = measure_text_width(
                    wrapped_line.text,
                    line_font_size,
                    layout.preferences,
                    layout.params,
                ) * scale
                target_width_px = (
                    layout.page_width_pt
                    - 2 * layout.params.side_margin_pt
                    - wrapped_line.first_line_indent_pt
                ) * scale
                extra_width_px = target_width_px - text_width_px
                extra_char_spacing_px = extra_width_px / (len(wrapped_line.text) - 1)
                if 0.01 < extra_char_spacing_px <= MAX_JUSTIFY_EXTRA_CHAR_SPACING_PT * scale:
                    line_char_spacing_px += extra_char_spacing_px
            for font_name, run_text in iter_font_runs(wrapped_line.text or " "):
                pixel_size = max(1, int(round(get_effective_font_size(font_name, line_font_size, layout.preferences) * scale)))
                font = self._load_preview_font(font_name, pixel_size)
                cursor_x = self._draw_preview_run(
                    draw,
                    cursor_x,
                    baseline_y,
                    run_text,
                    font,
                    fill=THEME["ink"],
                    char_spacing_px=line_char_spacing_px,
                    word_spacing_px=word_spacing_px,
                    stroke_width=max(1, int(round(pixel_size * 0.035))) if wrapped_line.bold else 0,
                )
            baseline_y += get_wrapped_line_leading(
                layout.font_size,
                layout.preferences,
                layout.params,
                wrapped_line,
            ) * scale
            if wrapped_line.paragraph_break_after and layout.params.paragraph_gap_pt > 0:
                baseline_y += layout.params.paragraph_gap_pt * scale

        return image

    def _render_preview_canvas(self) -> None:
        """Draw the current last-page text preview or a placeholder message."""

        if self.preview_canvas is None:
            return

        canvas = self.preview_canvas
        canvas.delete("all")
        canvas.update_idletasks()

        canvas_width = max(canvas.winfo_width(), 360)
        canvas_height = max(canvas.winfo_height(), 260)

        if self.current_preview_layout is None:
            canvas.create_text(
                canvas_width / 2,
                canvas_height / 2,
                text=self.preview_notice,
                width=max(260, canvas_width - 80),
                justify=tk.CENTER,
                fill=THEME["danger"] if self.preview_overflow else THEME["muted"],
                font=(self.ui_font_family, 12),
            )
            canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
            return

        layout = self.current_preview_layout
        outer_padding = 18
        footer_space = 34
        available_width = max(260, canvas_width - outer_padding * 2)
        available_height = max(320, canvas_height - outer_padding * 2 - footer_space)
        page_ratio = layout.page_width_pt / layout.page_height_pt
        render_width = min(available_width, available_height * page_ratio)
        render_height = render_width / page_ratio
        if render_height > available_height:
            render_height = available_height
            render_width = render_height * page_ratio
        page_left = (canvas_width - render_width) / 2
        page_top = outer_padding
        page_right = page_left + render_width
        page_bottom = page_top + render_height
        scale = render_width / layout.page_width_pt

        canvas.create_rectangle(
            page_left,
            page_top,
            page_right,
            page_bottom,
            fill=THEME["page"],
            outline=THEME["danger"] if self.preview_overflow else THEME["border"],
            width=2,
        )

        target_page_index = self.target_page_count - 1
        page_image = self._render_layout_page_image(
            layout,
            width_px=max(1, int(round(render_width))),
            height_px=max(1, int(round(render_height))),
            page_index=target_page_index,
        )
        self.preview_image = ImageTk.PhotoImage(page_image)
        canvas.create_image(page_left, page_top, image=self.preview_image, anchor="nw")

        if target_page_index >= layout.page_count:
            canvas.create_text(
                (page_left + page_right) / 2,
                (page_top + page_bottom) / 2,
                text="此页留白",
                fill=THEME["muted"],
                font=(self.ui_font_family, 14),
            )

        canvas.create_text(
            canvas_width / 2,
            page_bottom + 18,
            text=self.preview_notice,
            fill=THEME["danger"] if self.preview_overflow else THEME["muted"],
            font=(self.ui_font_family, 10),
        )
        canvas.configure(scrollregion=(0, 0, canvas_width, page_bottom + footer_space))

    def _load_watermark_font(self, pixel_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Load a bold-ish font for the PDF preview watermark."""

        for font_path in PREVIEW_WATERMARK_FONT_CANDIDATES:
            if not font_path.exists():
                continue
            try:
                return ImageFont.truetype(
                    str(font_path),
                    max(1, pixel_size),
                    index=get_font_subfont_index(font_path),
                )
            except OSError:
                continue
        return ImageFont.load_default()

    def _load_floating_menu_photo(self) -> ImageTk.PhotoImage | None:
        """Load the transparent PNG used by the viewport-pinned menu button."""

        if not FLOATING_MENU_IMAGE_PATH.exists():
            return None
        try:
            image = Image.open(FLOATING_MENU_IMAGE_PATH).convert("RGBA")
            return ImageTk.PhotoImage(image)
        except (OSError, tk.TclError):  # pragma: no cover - asset/runtime dependent
            return None

    def _get_cut_order_for_imposed_page(self, page_index: int) -> tuple[str, ...]:
        """Return the four source pages reached by cutting one imposed A4 side.

        ``get_layout_page_mapping`` is the same mapping used by ``impose.py``
        when it places source pages into the four A4 cells.  Keeping the
        watermark and the PDF generator on that single mapping prevents the
        preview from advertising a simple PDF sequence such as 1, 2, 3, 4...
        when the physical cut order is actually the 3A6/duplex order.
        """

        if not self._is_cutstack_mode() or page_index < 0:
            return ()

        source_page_count = max(1, self.target_page_count)
        padded_page_count = pad_page_count(source_page_count)
        mapping = get_layout_page_mapping(
            padded_page_count,
            layout_mode=self.layout_mode,
        )
        start = page_index * 4
        page_offsets = mapping[start:start + 4]
        if len(page_offsets) != 4:
            return ()
        return tuple(
            str(offset + 1) if offset < source_page_count else "—"
            for offset in page_offsets
        )

    def _get_pdf_preview_page_label(self, page_index: int, page_count: int) -> str:
        """Describe an imposed page by its physical A4 cutting order."""

        cut_order = self._get_cut_order_for_imposed_page(page_index)
        if cut_order:
            return "A4 裁切：" + " · ".join(cut_order)
        return str(page_index + 1) if page_count else ""

    def _add_pdf_preview_watermark(
        self,
        image: Image.Image,
        cut_order: tuple[str, ...],
    ) -> Image.Image:
        """Stamp one large light-blue number onto each imposed A6 cell.

        The four labels are placed using the same A4 cell rectangles as the
        imposition engine.  This keeps the visual guide attached to each small
        page after cutting instead of drawing one diagonal mark across the
        whole A4 sheet.
        """

        if len(cut_order) != 4:
            return image.convert("RGB")

        base = image.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        accent_rgb = tuple(
            int(THEME["accent"].lstrip("#")[index:index + 2], 16)
            for index in (0, 2, 4)
        )
        cell_rects = build_cell_rects()
        cell_coords = ((0, 0), (1, 0), (0, 1), (1, 1))

        for coord, label in zip(cell_coords, cut_order):
            if label == "—":
                continue
            rect = cell_rects[coord]
            center_x = (rect.x + rect.width / 2) / A4_WIDTH_PT * base.width
            center_y = (
                A4_HEIGHT_PT - (rect.y + rect.height / 2)
            ) / A4_HEIGHT_PT * base.height
            cell_width_px = rect.width / A4_WIDTH_PT * base.width
            cell_height_px = rect.height / A4_HEIGHT_PT * base.height
            # Make the cut-order marker fill the A6 cell while keeping
            # two-digit labels inside the same cell.  The width/height caps
            # are applied after choosing a deliberately large starting size,
            # so a single digit can occupy most of the A6 page.
            font_size = max(34, int(round(min(cell_width_px, cell_height_px) * 1.60)))
            font = self._load_watermark_font(font_size)
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            max_text_width = cell_width_px * 0.90
            max_text_height = cell_height_px * 0.84
            while (
                (text_width > max_text_width or text_height > max_text_height)
                and font_size > 34
            ):
                font_size -= 2
                font = self._load_watermark_font(font_size)
                bbox = draw.textbbox((0, 0), label, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            draw.text(
                (
                    center_x - text_width / 2 - bbox[0],
                    center_y - text_height / 2 - bbox[1],
                ),
                label,
                font=font,
                fill=accent_rgb + (PREVIEW_WATERMARK_ALPHA,),
            )

        return Image.alpha_composite(base, overlay).convert("RGB")

    def _draw_floating_menu(self) -> None:
        """Draw the transparent PNG control at the visible bottom-right corner."""

        canvas = self.pdf_preview_canvas
        if canvas is None or not canvas.winfo_exists():
            return

        canvas.delete("floating_menu")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 80 or height <= 80 or self.floating_menu_photo is None:
            return

        # Convert viewport coordinates to scrollregion coordinates.  This keeps
        # the control fixed while a taller PDF is scrolled, without introducing
        # a child widget or a solid rectangle over the document.
        center_x = canvas.canvasx(width - 36)
        center_y = canvas.canvasy(height - 36)
        canvas.create_image(
            center_x,
            center_y,
            image=self.floating_menu_photo,
            anchor="center",
            tags=("floating_menu",),
        )
        canvas.tag_raise("floating_menu")

    def _render_pdf_preview_canvas(self) -> None:
        """Draw the cached full PDF preview in two columns."""

        if self.pdf_preview_canvas is None:
            return

        canvas = self.pdf_preview_canvas
        canvas.delete("all")
        canvas.update_idletasks()

        canvas_width = max(canvas.winfo_width(), 360)
        canvas_height = max(canvas.winfo_height(), 260)
        outer_padding = 12
        column_gap = 16
        row_gap = 14
        page_label_space = 20
        footer_space = 26

        if not self.preview_source_images:
            canvas.create_text(
                canvas_width / 2,
                canvas_height / 2,
                text=self.pdf_preview_notice,
                width=max(260, canvas_width - 80),
                justify=tk.CENTER,
                fill=THEME["muted"],
                font=(self.ui_font_family, 12),
            )
            canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
            self._draw_floating_menu()
            return

        first_image = self.preview_source_images[0]
        page_ratio = first_image.width / first_image.height
        page_count = len(self.preview_source_images)
        row_count = (page_count + 1) // 2
        width_limit = max(140.0, (canvas_width - outer_padding * 2 - column_gap) / 2)
        height_budget = (
            canvas_height
            - outer_padding * 2
            - footer_space
            - row_count * page_label_space
            - max(0, row_count - 1) * row_gap
        )
        height_limit = max(96.0, height_budget / max(1, row_count))
        # A small safety factor leaves breathing room for the footer and makes
        # the complete PDF fit without the one-pixel bottom overflow seen on
        # the previous width-only layout.
        fit_scale = 0.96
        render_width = min(width_limit, height_limit * page_ratio) * fit_scale
        render_height = render_width / page_ratio
        content_width = min(canvas_width - outer_padding * 2, render_width * 2 + column_gap)
        content_left = (canvas_width - content_width) / 2
        y_positions: list[float] = []
        self.pdf_preview_images = []

        for index, source_image in enumerate(self.preview_source_images):
            column = index % 2
            row = index // 2
            page_left = content_left + column * (render_width + column_gap)
            page_top = outer_padding + row * (render_height + page_label_space + row_gap)
            page_right = page_left + render_width
            page_bottom = page_top + render_height
            y_positions.append(page_bottom)

            canvas.create_rectangle(
                page_left,
                page_top,
                page_right,
                page_bottom,
                fill=THEME["page"],
                outline=THEME["border"],
                width=2,
            )
            page_image = source_image.convert("RGB").resize(
                (max(1, int(round(render_width))), max(1, int(round(render_height)))),
                Image.LANCZOS,
            )
            if self._is_cutstack_mode():
                cut_order = self._get_cut_order_for_imposed_page(index)
                page_image = self._add_pdf_preview_watermark(
                    page_image,
                    cut_order=cut_order,
                )
            photo = ImageTk.PhotoImage(page_image)
            self.pdf_preview_images.append(photo)
            canvas.create_image(page_left, page_top, image=photo, anchor="nw")
            page_label = self._get_pdf_preview_page_label(index, page_count)
            canvas.create_text(
                (page_left + page_right) / 2,
                page_bottom + page_label_space / 2,
                text=page_label,
                fill=THEME["muted"],
                font=(self.ui_font_family, 8 if self._is_cutstack_mode() else 9),
            )

        footer_top = max(y_positions) + page_label_space
        canvas.create_text(
            canvas_width / 2,
            footer_top + footer_space / 2,
            text=self.pdf_preview_notice,
            fill=THEME["muted"],
            font=(self.ui_font_family, 10),
        )
        content_bottom = footer_top + footer_space
        canvas.configure(scrollregion=(0, 0, canvas_width, max(canvas_height, content_bottom + outer_padding)))
        self._draw_floating_menu()

    def _display_pdf_preview(self, pdf_path: Path) -> None:
        """Load all pages of a PDF into the in-app PDF preview pane."""

        if self.pdf_preview_canvas is None:
            return

        try:
            page_count = len(PdfReader(str(pdf_path)).pages)
            images = _convert_pdf_to_images(pdf_path, dpi=120)
            if not images:
                self._set_pdf_preview_notice("未能从 PDF 读取预览内容。")
                return

            self.pdf_preview_source_image = images[0]
            self.preview_source_images = images
            self.preview_page_var.set(f"PDF 预览：{pdf_path.name}")
            mode_label = "拼板 A4" if self._is_cutstack_mode() else A4_DUPLEX_LABEL
            self.pdf_preview_notice = f"{mode_label} PDF 预览：共 {page_count} 页"
            self._render_pdf_preview_canvas()
        except Exception as exc:
            self.status_var.set(f"PDF 预览失败：{exc}")
            self.preview_page_var.set("预览：失败")
            self._set_pdf_preview_notice(f"PDF 预览失败\n\n{exc}")

    def _refresh_pdf_preview_from_current_layout(self, *, show_messagebox_on_error: bool) -> None:
        """Generate the current full output PDF and refresh the in-app PDF pane."""

        if self.current_preview_layout is None:
            self._set_pdf_preview_notice("等待排版完成后生成 PDF 预览")
            return

        try:
            if self._is_cutstack_mode():
                self.status_var.set("正在生成拼板 A4 PDF 预览...")
                self._set_pdf_preview_notice("正在生成拼板 A4 PDF 预览...")
                self.root.update_idletasks()
                source_pdf = render_source_pdf(
                    self.current_preview_layout,
                    build_editor_source_path(),
                    total_pages=self.target_page_count,
                )
                preview_path = build_output_path(source_pdf)
                impose_cutstack_pdf(source_pdf, preview_path, layout_mode=self.layout_mode)
            else:
                self.status_var.set("正在生成双面 A4 PDF 预览...")
                self._set_pdf_preview_notice("正在生成双面 A4 PDF 预览...")
                self.root.update_idletasks()
                source_pdf = render_source_pdf(
                    self.current_preview_layout,
                    build_editor_a4_output_path(),
                    total_pages=self.target_page_count,
                )
                preview_path = source_pdf
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.last_preview_pdf_path = None
            self.last_preview_pdf_ready = False
            self.print_pdf_ready = False
            self._set_pdf_preview_notice("PDF 预览生成失败。")
            self.status_var.set(f"PDF 预览生成失败：{exc}")
            if show_messagebox_on_error:
                messagebox.showerror("PDF预览失败", str(exc), parent=self.root)
            return

        self.last_preview_pdf_path = preview_path
        self.last_preview_pdf_ready = True
        self.source_path = source_pdf
        self.print_source_path = source_pdf
        self.output_path = preview_path
        self.print_pdf_ready = preview_path.exists() and not self.preview_overflow
        self.source_path_var.set(str(source_pdf))
        self.output_path_var.set(str(preview_path))
        self._display_pdf_preview(preview_path)

    def _run_initial_search(self, *, show_messagebox_on_error: bool) -> None:
        """Run the one-time global search and cache the sequentially tuned result."""

        editor_text = self._get_editor_text()
        if not editor_text.strip():
            return

        self.status_var.set("已读取剪切板，正在按优先级搜索排版参数...")
        self._set_pdf_preview_notice("已读取剪切板\n正在搜索排版参数...")
        self.root.update_idletasks()

        try:
            normalized_text = normalize_editor_text(editor_text)
            self._normalize_current_target_page_count()
            searched_layout = choose_fitted_layout(
                normalized_text,
                self._current_font_preferences(),
                params=LayoutParameters(),
                target_pages=self.target_page_count,
                auto_tune_layout=True,
                page_mode=self._current_page_mode(),
            )
        except DocumentBuildError as exc:
            self.is_dirty = True
            self.status_var.set(str(exc))
            self._set_preview_notice(str(exc))
            self._set_pdf_preview_notice(f"排版失败\n\n{exc}")
            self._set_overflow_visual_state(False)
            self._update_button_states()
            if show_messagebox_on_error:
                messagebox.showerror("生成失败", str(exc), parent=self.root)
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.is_dirty = True
            self.status_var.set(str(exc))
            self._set_preview_notice(str(exc))
            self._set_pdf_preview_notice(f"排版失败\n\n{exc}")
            self._set_overflow_visual_state(False)
            self._update_button_states()
            if show_messagebox_on_error:
                messagebox.showerror("未知错误", str(exc), parent=self.root)
            return

        self.normalized_document_text = normalized_text
        self.base_font_size = searched_layout.font_size
        self.base_preferences = searched_layout.preferences
        self.base_layout_params = searched_layout.params
        self.manual_layout_params = searched_layout.params
        self.initial_target_page_count = self.target_page_count
        self._sync_layout_control_vars()
        self._render_preview_from_fixed_search(show_messagebox_on_error=show_messagebox_on_error)

    def _render_preview_from_fixed_search(self, *, show_messagebox_on_error: bool) -> None:
        """Render the last-page preview from cached search results only."""

        if not self.normalized_document_text or self.base_font_size is None or self.base_preferences is None:
            return

        self.status_var.set("排版参数已确定，正在生成 PDF 预览...")
        self._set_pdf_preview_notice("排版参数已确定\n正在生成 PDF 预览...")
        self.root.update_idletasks()

        try:
            self.manual_layout_params = get_print_safe_layout_parameters(
                self.manual_layout_params,
                self._current_page_mode(),
            )
            layout = build_text_layout(
                self.normalized_document_text,
                self.base_font_size,
                self.base_preferences,
                self.manual_layout_params,
                *self._current_page_dimensions(),
            )
        except DocumentBuildError as exc:
            self.is_dirty = True
            self.status_var.set(str(exc))
            self._set_preview_notice(str(exc))
            self._set_pdf_preview_notice("PDF 预览不可用")
            self._set_overflow_visual_state(True)
            self._update_button_states()
            if show_messagebox_on_error:
                messagebox.showerror("预览失败", str(exc), parent=self.root)
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.is_dirty = True
            self.status_var.set(str(exc))
            self._set_preview_notice(str(exc))
            self._set_pdf_preview_notice("PDF 预览不可用")
            self._set_overflow_visual_state(True)
            self._update_button_states()
            if show_messagebox_on_error:
                messagebox.showerror("未知错误", str(exc), parent=self.root)
            return

        self.result = None
        self.current_preview_layout = layout
        self.source_path = None
        self.print_source_path = None
        self.output_path = None
        self.print_pdf_ready = False
        self.page_usage_var.set(f"{layout.page_count}/{self.target_page_count}")
        self.font_size_var.set(
            f"英{layout.font_size * layout.preferences.latin_scale:.2f} / 中{layout.font_size * layout.preferences.cjk_scale:.2f} pt"
        )
        self.margin_var.set(
            f"侧{layout.params.side_margin_pt:.1f} / 上下{layout.params.vertical_margin_pt:.1f} pt"
        )
        self.source_path_var.set("-")
        self.output_path_var.set("-")
        self._set_overflow_visual_state(layout.page_count > self.target_page_count)
        if self.preview_overflow:
            self.status_var.set(f"已超出最后一页边界：实际 {layout.page_count}/{self.target_page_count} 页。")
        else:
            self.status_var.set(f"当前自动/手动排版结果：{layout.page_count}/{self.target_page_count} 页。双击 Enter 直接打印。")
        self.preview_notice = f"最后一页文本预览：目标第 {self.target_page_count} 页"
        if self.preview_overflow:
            self.preview_notice += " | 已超界"
        self.is_dirty = False
        self._render_preview_canvas()
        self._refresh_pdf_preview_from_current_layout(show_messagebox_on_error=show_messagebox_on_error)
        if self.pdf_preview_canvas is not None:
            self.pdf_preview_canvas.focus_set()
        self._update_button_states()

    def fit_document_to_pages(
        self,
        *,
        show_empty_error: bool = True,
        show_messagebox_on_error: bool = True,
    ) -> None:
        """Run the one-time auto search, then cache it for manual preview updates."""

        editor_text = self._get_editor_text()
        if not editor_text.strip():
            if show_empty_error:
                messagebox.showerror("内容为空", "请先输入或粘贴文档内容。", parent=self.root)
            return

        self._cancel_auto_fit()
        self._run_initial_search(show_messagebox_on_error=show_messagebox_on_error)

    def reset_layout_to_initial_search(self) -> None:
        """Restore the cached initial-search result and page target."""

        if self.base_font_size is None or not self.normalized_document_text:
            return

        self.target_page_count = self.initial_target_page_count
        self.manual_layout_params = self.base_layout_params
        self._sync_layout_control_vars()
        self._render_preview_from_fixed_search(show_messagebox_on_error=False)

    def preview_source_pdf(self) -> None:
        """Generate and open the last-page PDF preview from the cached layout."""

        if self.current_preview_layout is None:
            return
        try:
            preview_path = render_source_pdf(
                self.current_preview_layout,
                build_editor_preview_path(),
                total_pages=self.target_page_count,
                page_indices=[self.target_page_count - 1],
            )
            self.last_preview_pdf_path = preview_path
            self.last_preview_pdf_ready = True
            self.source_path = preview_path
            self.source_path_var.set(str(preview_path))
            self.preview_page_var.set(f"最后一页 PDF 预览：{preview_path.name}")
            self.status_var.set("最后一页 PDF 预览已生成并打开，可用于单独核对。")
            open_pdf_for_manual_print(preview_path)
        except (PrintCommandError, FileNotFoundError) as exc:
            messagebox.showerror("预览失败", str(exc), parent=self.root)
        except Exception as exc:  # pragma: no cover - defensive UI path
            messagebox.showerror("预览失败", str(exc), parent=self.root)

    def build_print_pdf(self, *, open_after_build: bool = False) -> None:
        """Generate the imposed print PDF from the cached manual layout."""

        if self.current_preview_layout is None:
            return
        if self.preview_overflow:
            message = "当前内容已超出最后一页边界，请先调整参数直到不标红后再打印。"
            self.status_var.set(message)
            if open_after_build:
                messagebox.showwarning("无法打印", message, parent=self.root)
            return

        self.status_var.set("正在生成打印 PDF，请稍候...")
        self.root.update_idletasks()

        try:
            if self._is_cutstack_mode():
                source_pdf = render_source_pdf(
                    self.current_preview_layout,
                    build_editor_source_path(),
                    total_pages=self.target_page_count,
                )
                output_pdf = build_output_path(source_pdf)
                imposition_result = impose_cutstack_pdf(source_pdf, output_pdf, layout_mode=self.layout_mode)
                status_message = imposition_result.status_message
            else:
                output_pdf = render_source_pdf(
                    self.current_preview_layout,
                    build_editor_a4_output_path(),
                    total_pages=self.target_page_count,
                )
                source_pdf = output_pdf
                status_message = (
                    f"双面 A4 PDF 完成：正文 {self.current_preview_layout.page_count}/{self.target_page_count} 页，"
                    f"按 2 页双面倍数输出 {self.target_page_count} 页。"
                )
        except DocumentBuildError as exc:
            self.print_pdf_ready = False
            self.print_source_path = None
            self.output_path = None
            self.output_path_var.set("-")
            self.status_var.set(str(exc))
            self._update_button_states()
            messagebox.showerror("生成失败", str(exc), parent=self.root)
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.print_pdf_ready = False
            self.print_source_path = None
            self.output_path = None
            self.output_path_var.set("-")
            self.status_var.set(str(exc))
            self._update_button_states()
            messagebox.showerror("未知错误", str(exc), parent=self.root)
            return

        self.print_source_path = source_pdf
        self.output_path = output_pdf
        self.output_path_var.set(str(output_pdf))
        self.print_pdf_ready = bool(output_pdf.exists())
        self.status_var.set(status_message)
        self._update_button_states()
        if open_after_build and self.print_pdf_ready:
            self.print_imposed_pdf()

    def preview_imposed_pdf(self) -> None:
        """Open the imposed print PDF."""

        if not self.output_path or not self.print_pdf_ready:
            return
        try:
            open_pdf_for_manual_print(self.output_path)
        except (PrintCommandError, FileNotFoundError) as exc:
            messagebox.showerror("预览失败", str(exc), parent=self.root)

    def print_imposed_pdf(self) -> None:
        """Open the imposed PDF and remind the user about print settings."""

        if not self.output_path or not self.print_pdf_ready:
            return

        self._record_current_font_size_history()

        messagebox.showinfo(
            "打印提示",
            "即将打开打印 PDF。\n\n"
            f"{self._current_print_hint()}\n"
            + ("程序输出已经完成拼版，不需要额外设置 booklet 或多页并打。" if self._is_cutstack_mode() else "程序输出的是按页序排列的双面 A4 PDF，不需要额外设置多页并打。"),
            parent=self.root,
        )
        self.preview_imposed_pdf()

    def direct_print_imposed_pdf(self, *, show_success_message: bool = True) -> None:
        """Send the imposed PDF directly to the default printer."""

        if not self.output_path or not self.print_pdf_ready:
            return

        try:
            direct_print_pdf(
                pdf_path=self.output_path,
                printer_name=None,
                sides="two-sided-long-edge",
                copies=1,
                number_up=1,
            )
        except PrintCommandError as exc:
            messagebox.showerror("打印失败", str(exc), parent=self.root)
            return

        self._record_current_font_size_history()

        if show_success_message:
            messagebox.showinfo(
                "已发送打印",
                "打印 PDF 已发送到默认打印机。\n\n"
                f"{self._current_print_hint()}",
                parent=self.root,
            )

    def open_output_directory(self) -> None:
        """Open the output directory in the desktop's file manager."""

        output_dir = self.output_path.parent if self.output_path else DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            open_path_with_default_app(output_dir)
        except (PrintCommandError, FileNotFoundError) as exc:
            messagebox.showerror("打开目录失败", str(exc), parent=self.root)


def launch_app() -> None:
    """Create and run the Tkinter desktop window."""

    root = tk.Tk()

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(
        "Shell.Vertical.TScrollbar",
        troughcolor=THEME["panel_strong"],
        background=THEME["button"],
        darkcolor=THEME["button"],
        lightcolor=THEME["button"],
        bordercolor=THEME["panel_strong"],
        arrowcolor=THEME["ink"],
        arrowsize=12,
    )
    style.map(
        "Shell.Vertical.TScrollbar",
        background=[("active", THEME["button_hover"])],
        arrowcolor=[("disabled", THEME["disabled_fg"])],
    )

    CutStackBookletPrinterApp(root)
    root.mainloop()
