# many_tools

Windows 实用工具集合，包含六个桌面小工具。界面右下角统一显示低调版权标识「© 大鹏Payne」。

## 项目结构

```
many_tools/
├── shared/                 # 多工具共用（版权 UI、打包脚本，见 shared/README.md）
├── dist/                   # 打包输出的 exe（gitignore，本地生成）
├── recoil_macro/           # 压枪 / 跟随辅助
├── search_tool_app/        # 目录字符串查询
├── protocol_manager/       # 本地 URL 协议管理
├── network_auth_manager/   # 网络认证自动保活
├── port_manager/           # 端口占用查询与释放
├── pubg_map_tool/          # PUBG 地图同步与游戏覆盖层
└── requirements.txt
```

## 工具列表

### 1. 压枪宏 (recoil_macro)

Windows 压枪 / 跟随辅助工具。

**功能：**

- 压枪模式：按住右键激活，按住左键按方案下压鼠标
- 跟随模式：按住右键激活，按住左键跟踪屏幕目标
- 支持多套压枪方案（间隔、移动距离）保存与切换

**技术栈：** Python + OpenCV + ctypes + pynput + tkinter

**目录结构：** `main.py`（入口）、`config.py`（方案配置）、`follow_core.py`（跟随算法）、`finalize_build.py`（打包后重命名）

**打包输出：** `dist\鼠标辅助工具.exe`

### 2. 目录字符串查询工具 (search_tool_app)

在指定根目录中按目录名、文件名或文件内容搜索。

**功能：**

- 按目录名 / 文件名 / 文件内容搜索
- 可配置忽略目录、大小写、线程数等

**技术栈：** Python + tkinter

**打包输出：** `dist\目录字符串查询工具.exe`

### 3. 本地协议配置管理器 (protocol_manager)

Windows 自定义 URL 协议（`HKCU\Software\Classes`）管理。

**功能：**

- 枚举、新建、编辑、删除 URL 协议
- 测试唤起（`scheme://`）

**技术栈：** Python + tkinter + winreg

**打包输出：** `dist\本地协议配置管理器.exe`

### 4. 网络认证自动保活工具 (network_auth_manager)

校园网 / 企业网等 Web 认证环境自动保活（单实例 + 系统托盘）。

**功能：**

- 定时探测外网，掉线后自动提交登录
- 静默 / 显示执行模式；支持启动时自动开始监听

**技术栈：** Python + tkinter + urllib + pystray + Pillow

**打包输出：** `dist\网络认证自动保活工具.exe`

### 5. 端口管理工具 (port_manager)

查询端口占用并按进程释放（**需管理员权限**）。

**功能：**

- 列出端口、PID、进程名；支持筛选与自动刷新
- 释放选中端口或按输入端口号释放

**技术栈：** Python + tkinter + subprocess + ctypes

**打包输出：** `dist\端口管理工具.exe`

> 打包后的 exe 在非管理员下会请求 UAC 提权后退出，请右键「以管理员身份运行」。

### 6. PUBG 地图工具 (pubg_map_tool)

从 [pubg.im/maps](https://pubg.im/maps) 同步带 8x8 坐标点位的地图，支持查看、导出与游戏覆盖层。

**功能：**

- 一键从 pubg.im 下载全部地图（8x8 详细版）
- 地图列表、缩放预览、PNG 导出
- 桌面置顶半透明覆盖层，可调透明度与比例，地图区域鼠标穿透
- 全局快捷键显示/隐藏覆盖层（默认 `右 Ctrl+M`，可在控制面板自定义）

**技术栈：** Python + tkinter + Pillow + urllib + pynput

**目录结构：**

- `main.py` — 入口与主界面
- `map_catalog.py` / `map_fetcher.py` — 地图元数据与下载
- `preview_cache.py` — `data/previews` 预览缓存
- `overlay_window.py` / `overlay_settings.py` / `overlay_hotkey.py` — 覆盖层
- `app_icon.py` / `generate_icons.py` / `finalize_build.py` — 图标与打包收尾
- `pubg_map_tool.spec` — PyInstaller 规格（输出到仓库根目录 `dist/`）
- `build_exe.bat` — 一键打包

**打包输出：** `dist\PUBG地图工具.exe`

**本地数据（`data/`，已 gitignore）：** `maps/`、`previews/`、`thumbs/`、`manifest.json`、`overlay_settings.json`

## 共用目录 `shared/`

| 文件 | 用途 |
|------|------|
| `tool_branding.py` | 各工具界面版权标识 |
| `build_conda_common.ps1` | PyInstaller：Miniconda 检测、Conda DLL、Tcl/Tk 数据、`--collect-all tkinter` |
| `rthook_tkinter_runtime.py` | 打包 exe 运行时 DLL / `TCL_LIBRARY` / `TK_LIBRARY` |
| `finalize_dist_rename.py` | 将 `dist` 下 ASCII 构建名 exe 重命名为中文文件名 |

详见 [shared/README.md](shared/README.md)。各工具源码通过将 `shared/` 加入 `sys.path` 导入 `tool_branding`；`build_exe.ps1` 通过 dot-source 引用 `build_conda_common.ps1`。

## 环境要求

- Windows 10/11
- **推荐** [Miniconda](https://docs.conda.org/en/latest/miniconda.html) 或 Anaconda 的 Python 3.11+（打包脚本会优先使用，并自动补齐 Tcl/Tk 等 DLL）
- 系统 `PATH` 中的 `python` 若为微软商店占位程序，请改用上述环境或各工具 `build_exe.bat`（已改为调用 PowerShell 脚本）

## 安装依赖

在仓库根目录执行：

```bash
pip install -r requirements.txt
```

压枪宏、网络认证、地图工具等会用到 OpenCV、Pillow、pystray、pynput 等，以 `requirements.txt` 为准。

## 开发与运行

进入对应工具目录，用 Python 直接运行入口文件，例如：

```bash
python search_tool_app/main.py
python pubg_map_tool/main.py
```

地图工具首次使用可在界面中「更新全部地图」；`data/` 目录会自动创建。

## 打包为可执行文件

### 通用说明

| 项目 | 说明 |
|------|------|
| 入口脚本 | 各工具目录下的 `build_exe.bat`（双击）或 `build_exe.ps1` |
| Python | 打包脚本自动选用 Miniconda / Anaconda，避免商店版 `python` 导致 pip 失败 |
| 依赖补齐 | `shared/build_conda_common.ps1` 注入 Tcl/Tk 与 Conda 运行库，解决 exe 启动缺 DLL |
| 输出目录 | 仓库根目录 `dist/`（已在 `.gitignore`） |
| 中文文件名 | 查询 / 协议 / 端口 / 网络认证工具由 `finalize_dist_rename.py` 重命名；压枪宏与地图工具在各自目录内 `finalize_build.py` 处理 |

### 各工具打包命令

在资源管理器中双击对应 `build_exe.bat`，或在仓库根目录执行 PowerShell：

```powershell
.\search_tool_app\build_exe.ps1
.\protocol_manager\build_exe.ps1
.\port_manager\build_exe.ps1
.\network_auth_manager\build_exe.ps1
.\recoil_macro\build_exe.ps1
.\pubg_map_tool\build_exe.bat    # 内含图标生成、PyInstaller、冒烟测试
```

### 打包产物一览

| 工具 | 输出 exe |
|------|----------|
| 压枪宏 | `dist\鼠标辅助工具.exe` |
| 目录查询 | `dist\目录字符串查询工具.exe` |
| 协议管理 | `dist\本地协议配置管理器.exe` |
| 网络认证 | `dist\网络认证自动保活工具.exe` |
| 端口管理 | `dist\端口管理工具.exe` |
| PUBG 地图 | `dist\PUBG地图工具.exe` |

打包过程中会在各工具目录生成 `*.spec` 与 `build/` 缓存（已 gitignore），可重复执行脚本覆盖构建。

## 常见问题

**exe 提示缺 Tcl/Tk 或 DLL：** 请用更新后的 `build_exe.bat` 重新打包，确保走 `shared/build_conda_common.ps1`。

**bat 双击后 pip 失败：** 未检测到 Miniconda；请安装 Miniconda 或将可用 `python.exe` 加入 PATH。

**重命名失败 / 拒绝访问：** 关闭正在运行的同名 exe 后重新打包。

**网络认证提示已在运行：** 仅允许单实例，退出托盘或任务管理器中的旧进程后再开。
