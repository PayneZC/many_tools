# many_tools

Windows 实用工具集合，包含五个桌面工具：

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

### 4. 网络认证自动保活工具 (network_auth_manager)
用于校园网/企业网等需要 Web 认证的网络环境自动保活。

**功能：**
- 定时访问外网地址判断是否掉线
- 检测到掉线后通过爬虫方式提交账号密码并触发登录
- 支持静默执行和显示执行两种模式（显示模式仅用于排查）
- 固定使用内置认证地址与探测地址，仅维护账号密码和检测频率配置

**技术栈：** Python + tkinter + urllib + pystray + pillow

### 5. 端口管理工具 (port_manager)
Windows 端口占用查询与释放工具。

**功能：**
- 查询当前系统端口占用情况
- 按端口号筛选并定位进程
- 一键释放选中端口或按输入端口释放
- 支持自动定时刷新占用状态

**技术栈：** Python + tkinter + subprocess + ctypes

## 环境要求

- Python 3.x
- Windows 操作系统

## 安装依赖

```bash
pip install -r requirements.txt
```

## 打包为可执行文件

每个工具目录下都有打包脚本（`.bat` / `.ps1`）：

- `recoil_macro/build_exe.bat` - 打包压枪宏
- `search_tool_app/build_exe.bat` - 打包目录查询工具
- `protocol_manager/build_exe.bat` - 打包协议管理器
- `network_auth_manager/build_exe.bat` - 打包网络认证自动保活工具
- `port_manager/build_exe.bat` - 打包端口管理工具

运行对应脚本即可生成独立的 `.exe` 到 `dist/` 目录，并在工具目录下自动生成对应 `.spec` 文件。
