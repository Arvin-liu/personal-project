# CutStack Booklet Printer

CutStack Booklet Printer lays out plain text as paginated A6 PDFs and can impose pages onto A4 sheets for duplex printing. It also supports ordinary A4 output, PDF preview, and optional direct printing through the local print system.

This is a personal project. The repository contains source code, project structure, and the components needed to build the app. It does not contain the publisher's printer configuration, user documents, generated PDFs, launch tokens, virtual environments, or a prebuilt app bundle.

## How it works

1. Enter or paste text in the editor.
2. Choose a target page count and layout settings.
3. The app creates a paginated A6 source PDF.
4. Choose A4 output or 2×2 cut-and-stack imposition.
5. Preview the resulting PDF, then print it using the device's normal duplex settings.

Generated files are saved under `~/cutstack-booklet-printer/output/` by default. The output directory is created on the user's computer when needed.

## Main components

- `main.py`: app entry point and single-instance guard.
- `ui.py`: Tkinter editor, layout controls, PDF preview, and print actions.
- `editor_document.py`: text normalization, pagination, font selection, and source PDF generation.
- `impose.py`: A4 page imposition and PDF output.
- `printer.py`: PDF opening, preview rendering support, and optional CUPS printing.
- `assets/`: app icon and menu artwork.
- `requirements.txt`: Python package requirements.
- `run.sh`, `launcher_guard.sh`: local source launcher and its minimal helper.
- `build_cutstack_app.sh`, `start_cutstack_booklet_printer.sh`, `install_cutstack_app.sh`: macOS app build, launch, and install scripts.

## Requirements

- Python 3 with Tk support.
- Packages listed in `requirements.txt`.
- macOS or Linux desktop tools for opening PDFs; CUPS is needed for direct printing.
- Poppler is optional. When available, it can be used for PDF preview rendering.

Install Python dependencies from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the source version with:

```bash
./run.sh
```

On macOS, `./start_cutstack_booklet_printer.sh` builds the app bundle on first use and opens it. After changing source files, run `./build_cutstack_app.sh` to rebuild; `./install_cutstack_app.sh` rebuilds and installs the bundle in Applications. Building an app bundle requires macOS build tools such as `sips` and `iconutil`.

The included code is a source release, not a verified prebuilt distribution. If it fails on a particular system or lacks a required component, users can ask their own Agent to inspect the environment, supply compatible dependencies, and rebuild it.

## License

This project follows the repository's [CC BY-NC-SA 4.0 license](../LICENSE). See the repository [README](../README.md) and [NOTICE](../NOTICE.md) for attribution and scope. Python packages and system tools remain under their own licenses.
