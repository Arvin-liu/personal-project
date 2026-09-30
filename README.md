# 英文阅读器 · 个人项目

© 2026 Arvin-liu. 许可证和署名要求见 [NOTICE](NOTICE.md) 与 [LICENSE](LICENSE)。

这是一个基于 Python 和 Tkinter 的英文阅读器个人项目，提供英文文章阅读与朗读、网易有道查词、阅读历史和词汇复习等功能。

本仓库只公开项目架构、实现源码和必要的构建组件。它是个人项目，不承诺在所有电脑上开箱即用。

## 仓库包含什么

| 路径 | 作用 |
| --- | --- |
| `app.py` | 阅读器界面、文章与词典模式、查词、朗读、历史和 AI 路由 |
| `hermes_fast_oneshot.py` | 调用本机 Hermes 配置的轻量适配器 |
| `launcher_guard.sh` | 本项目启动器所需的令牌、进程和 Python 查找辅助函数 |
| `assets/app-icon.svg` | 应用图标源文件 |
| `build_ebook_reader_app.sh` | 在 macOS 上构建应用包 |
| `install_ebook_reader_app.sh` | 构建并安装 macOS 应用 |
| `start_ebook_reader.sh` | macOS 源码启动辅助脚本 |
| `uninstall_ebook_reader_app.sh` | 卸载 macOS 应用包 |

## 隐私与运行环境

仓库不包含 API Key、访问令牌、Hermes 登录配置、个人阅读记录、文章历史、缓存、语音模型、生成的应用包或本机启动令牌。可选 AI 服务从使用者本机环境读取凭据，例如 `DEEPSEEK_API_KEY`、`GEMINI_API_KEY` 和 `AGNES_API_KEY`；不要把这些值提交到仓库。

运行时可能需要使用者自行安装带 Tk 的 Python 3、Piper 与相应语音模型、Hermes 及已配置的模型服务。查词需要网络连接。上述账号、凭据和模型文件均由使用者自行配置，本仓库不提供。

macOS 构建需要 macOS 13 或更高版本，以及 Python 3/Tk。可尝试在仓库目录运行：

```bash
./install_ebook_reader_app.sh
```

该项目当前没有提供经过验证的 Linux 应用包。若运行失败、缺少必要组件，或需要在其他系统上构建，请使用者让自己的 Agent 检查本机环境、补齐依赖或调整启动器后重新编译。

普通查词只请求有道词典；只有使用者点击查词窗口中的放大镜时才请求 AI 语义解释。

## 许可

本项目原创源码和文档按 **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International（CC BY-NC-SA 4.0）** 发布：允许非商业使用、修改、编译和再发布；再发布时须注明来源、提供许可链接、说明改动，并将改编内容按相同许可发布。完整条款见 [LICENSE](LICENSE) 和 [官方许可页](https://creativecommons.org/licenses/by-nc-sa/4.0/)。再发布时请保留 [NOTICE](NOTICE.md)。第三方组件及服务不在本项目许可范围内，仍适用各自条款。

Creative Commons [官方说明](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software)不推荐将 CC 许可用于软件，因为它没有覆盖软件专属的源码分发和专利条款。软件专用的非商业许可证可参考 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)，但它没有 CC BY-NC-SA 4.0 明确的“改编后相同许可”条款。此处按项目发布者的选择采用 CC BY-NC-SA 4.0。因该许可限制商业用途，根据 [OSI 开源定义第 6 条](https://opensource.org/osd)，本仓库属于公开源码的个人项目，不称为 OSI 定义的开源软件。
