# shared

各小工具共用的代码与打包辅助，**不要删除**。

| 文件 | 用途 |
|------|------|
| `tool_branding.py` | 界面右下角版权标识「© 大鹏Payne」 |
| `build_conda_common.ps1` | PyInstaller 打包：Miniconda、Tcl/Tk DLL 与数据目录 |
| `rthook_tkinter_runtime.py` | 打包后 exe 运行时设置 DLL / Tcl/Tk 路径 |
| `finalize_dist_rename.py` | 将 `dist/*.exe` 从 ASCII 构建名重命名为中文文件名 |

各工具 `build_exe.ps1` 通过 `. shared\build_conda_common.ps1` 引用本目录。
