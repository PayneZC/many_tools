# many_tools

Windows 实用工具集合，包含三个桌面工具：

## 工具列表

### 1. 压枪宏 (recoil_macro)
Windows 压枪宏工具，基于 Python 实现。

**功能：**
- 按住鼠标右键启用压枪开关
- 开关生效时，按住鼠标左键持续向下移动鼠标

**技术栈：** Python + ctypes + pynput + tkinter

### 2. 目录字符串查询工具 (search_tool_app)
目录搜索工具，支持在指定目录中快速查找文件和内容。

**功能：**
- 按目录名搜索
- 按文件名搜索
- 按文件内容搜索
- 支持排除指定目录

**技术栈：** Python + tkinter

### 3. 本地协议配置管理器 (protocol_manager)
Windows 自定义 URL 协议注册表管理工具。

**功能：**
- 枚举系统已注册的 URL 协议
- 注册新的自定义 URL 协议
- 编辑/删除现有协议配置

**技术栈：** Python + tkinter + winreg

## 环境要求

- Python 3.x
- Windows 操作系统

## 安装依赖

```bash
pip install -r requirements.txt
```

## 打包为可执行文件

每个工具目录下都有打包脚本：

- `recoil_macro/build_exe.bat` - 打包压枪宏
- `search_tool_app/build_exe.bat` - 打包目录查询工具
- `protocol_manager/build_exe.bat` - 打包协议管理器

运行对应的 .bat 文件即可生成独立的 .exe 文件到 `dist/` 目录。
