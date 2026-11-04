# Finale to MusicXML（本地版）

把 Finale 的 MUSX 和部分旧 MUS 乐谱转换为 MXL（压缩的 MusicXML）。
这是乐谱格式转换工具，不是音频转换或扫描识谱工具。界面为日语。

## 使用

从 [Releases](https://github.com/g0732171/finale-to-musicxml/releases) 下载 Windows 或 Mac ZIP，
完整解压。Windows 双击 `Start-Windows.cmd`，Mac 双击 `Start-Mac.command`。
成品包自带运行环境，无需安装 Python 或 Finale，转换时不联网。

入口有“单个文件”和“选择文件夹”两种。结果保存到原文件或文件夹旁边新建的
`原名称_変換済み` 文件夹，只生成 MXL；保留子文件夹结构，不改原件、不覆盖已有结果。

## 来源与贡献

核心转换能力来自 **musx2mxl** 和 **finale-file-parser**，乐谱预览来自
**OpenSheetMusicDisplay**。感谢这些项目的作者。我们补充了便携本地部署、原生文件夹
选择、批量保存、日语界面、兼容修正和测试；不把上游解析算法称作自行原创。

源码只包含本地版，不包含网络版部署、客户乐谱、客户测试资料、服务器地址或密钥。
新增代码使用 MIT 许可证，上游项目保留各自许可证、署名和声明。

## 限制

只支持部分旧 MUS 结构，不能保证所有历史 Finale 文件都能读取，也不保证版式和所有
符号完整保留。请核对音符、移调、记号、分谱名称和大谱表。对无法验证的关键结构会
明确报未支持。版本号模拟测试不等于相应年代的真实文件已全面验证。

Windows 转换流程已验证；Mac 包尚未进行实际 Mac 启动和原生选择窗口测试。
源代码运行、构建、测试和完整署名说明见 [英文 README](README.md)。
