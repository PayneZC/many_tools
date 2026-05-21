# PUBG 辅助工具（地图 + 压枪）

在同一窗口中整合 PUBG 地图能力与压枪鼠标辅助。

## 功能

- **地图**：列表、更新全部/当前、预览、导出、游戏覆盖层。
- **压枪**：方案列表管理、首次/递增下移距离、压枪间隔、鼠标功能总开关、全局快捷键切换总开关。
- **托盘**：关闭窗口后最小化到系统托盘，可恢复界面或退出。
- **打赏**：展示微信/支付宝收款码。

操作：按住右键激活，按住左键压枪；双击方案列表可设为当前。第 1 次使用首次移动，之后为 `递增基数 + 递增次数 × 递增距离`（次数有上限）。

## 运行

```powershell
pip install -r requirements.txt
python fusion_tool/main.py
```

## 图标

小鸡图标由脚本生成：

```powershell
python fusion_tool/generate_icons.py
```

## 数据目录

持久化均在程序执行目录下的 `data/`：

| 文件 | 说明 |
|------|------|
| `data/manifest.json` | 地图清单 |
| `data/maps/`、`data/previews/` | 地图与预览 |
| `data/overlay_settings.json` | 覆盖层配置 |
| `data/recoil_presets.json` | 压枪方案 |
| `data/app_settings.json` | 鼠标辅助快捷键等全局设置 |

## 打包

```bat
fusion_tool\build_exe.bat
```

产物：`dist\PUBG辅助工具.exe`
