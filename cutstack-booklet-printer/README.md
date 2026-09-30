# 小册子拼版打印机（CutStack Booklet Printer）

这是一款桌面排版工具，可以把输入的纯文本排成 A6 页面，再按 2×2 方式拼到 A4 纸上进行双面打印。它也支持常规 A4 输出、PDF 预览，以及通过本机打印系统直接打印。

这是一个个人项目。仓库只包含源代码、项目结构和构建应用所需的组件，不包含作者的打印机配置、用户文档、生成的 PDF、运行时启动令牌、虚拟环境或预编译应用包。

## 工作流程

1. 在编辑区输入或粘贴文本。
2. 选择目标页数和排版设置。
3. 程序生成分页后的 A6 源 PDF。
4. 选择常规 A4 输出，或 2×2 小册子拼版。
5. 预览生成的 PDF，再按打印机的常规双面打印设置进行打印。

生成文件默认保存在 `~/cutstack-booklet-printer/output/`。程序会在使用者的电脑上按需创建此目录。

## 主要文件

- `main.py`：程序入口和单实例检查。
- `ui.py`：Tkinter 编辑界面、排版设置、PDF 预览和打印操作。
- `editor_document.py`：文本整理、分页、字体选择和源 PDF 生成。
- `impose.py`：A4 页面拼版和 PDF 输出。
- `printer.py`：打开 PDF、预览渲染和可选的 CUPS 打印。
- `assets/`：应用图标和菜单图片资源。
- `requirements.txt`：Python 依赖清单。
- `run.sh`、`launcher_guard.sh`：源码启动脚本及其辅助组件。
- `build_cutstack_app.sh`、`start_cutstack_booklet_printer.sh`、`install_cutstack_app.sh`：macOS 应用包的构建、启动和安装脚本。

## 运行环境和依赖

- 安装了 Tk 支持的 Python 3。
- 安装 `requirements.txt` 中列出的 Python 依赖。
- macOS 或 Linux 桌面环境及其 PDF 打开工具；直接打印需要 CUPS。
- Poppler 为可选组件。安装后可用于 PDF 预览渲染。

在本目录中创建 Python 环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 启动和构建

用源码启动：

```bash
./run.sh
```

在 macOS 上，首次运行 `./start_cutstack_booklet_printer.sh` 时会构建应用包并打开。修改源码后，先运行 `./build_cutstack_app.sh` 重新构建；运行 `./install_cutstack_app.sh` 会重新构建并安装到“应用程序”目录。构建 macOS 应用包需要 `sips`、`iconutil` 等系统工具。

当前仓库发布的是源码，不附带经过验证的预编译应用。如果在特定系统上运行失败或缺少组件，请使用者让自己的 Agent 检查本机环境、补齐兼容依赖并重新构建。

## 许可

本项目遵循仓库的 [CC BY-NC-SA 4.0 许可](../LICENSE)。署名和许可范围说明见仓库的 [首页](../README.md) 与 [NOTICE](../NOTICE.md)。Python 依赖包和系统工具仍分别遵循其自身许可。
