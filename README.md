# 个人项目 | 英文阅读器与小册子拼版打印机

© 2026 Arvin-liu. 许可证与署名要求见 [NOTICE](NOTICE.md) 和 [LICENSE](LICENSE)。

这里汇集个人项目的源码架构和必要构建组件。仓库不承诺在所有电脑上开箱即用；若运行失败或缺少依赖，请使用者让自己的 Agent 检查环境、补齐组件或重新编译。

## 项目

| 目录 | 项目 | 简介 |
| --- | --- | --- |
| 根目录 | 英文阅读器 | 英文文章阅读、朗读、普通查词、手动 AI 解释、阅读历史与词汇复习。普通查词不会自动调用 AI，点击查词窗口中的放大镜才请求 AI。 |
| [`cutstack-booklet-printer/`](cutstack-booklet-printer/README.md) | 小册子拼版打印机 | 将文本排成 A6 PDF，支持常规 A4 输出、2×2 拼版、PDF 预览和系统打印。 |

## 隐私与范围

仓库只包含源码、项目说明和必要构建组件，不包含 API Key、访问令牌、个人路径、用户文章与阅读记录、打印文档、缓存、运行时启动令牌、虚拟环境或预编译应用包。阅读器的可选 AI 连接从使用者自己的本机配置读取凭据；不要将凭据提交到仓库。打印机项目只在使用者本机生成文档和输出 PDF。

如果某个平台缺少必要组件，或构建、运行失败，请使用者让自己的 Agent 根据本机环境补齐依赖或修改启动器后重新编译。本仓库没有随附已验证的跨平台二进制发行包。

## 许可

本仓库原创源码和文档按 [CC BY-NC-SA 4.0](LICENSE) 发布。再发布时须注明来源、提供许可链接、说明改动，并将改编内容按相同许可发布。请保留 [NOTICE](NOTICE.md)。第三方软件包、系统工具、服务和其材料仍适用各自许可。

Creative Commons [官方说明](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software)不推荐将 CC 许可用于软件，因为它没有覆盖软件专属的源码分发和专利条款。软件专用的非商业许可证可参考 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)，但它没有 CC BY-NC-SA 4.0 明确的“改编后相同许可”条款。此处按项目发布者的选择采用 CC BY-NC-SA 4.0。由于许可限制商业用途，本仓库是公开的个人源码项目，不属于 OSI 定义的开源软件。
