# Noodle Fun Finance（财务结算软件 / Buchhaltung）

Windows 桌面软件：记录每日营业额（现金、刷卡、Lieferando、foodora、wolt，毛额）和支出，
月度汇总，导出日报/月报 PDF，界面中文/德语切换，支持从 GitHub 自动检测并安装更新。

## 首次上传 GitHub
1. 新建 **public** 仓库，例如 `noodlefun-finance`，把本文件夹全部内容推送上去。
2. `nffinance/version.py` 里的 `GITHUB_REPO` 已设为 `codex112026/noodlefun-finance`。
3. 发布第一个版本：
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
   GitHub Actions 会自动打包，并在 Releases 页面生成 `NoodleFunFinance-Setup.exe`。
4. 在 Windows 上下载安装 Setup.exe 即可使用（安装到当前用户目录，不需要管理员权限）。

## 发布更新
改完代码提交后，打一个更高版本号的 tag（如 `v1.0.1`）并推送。已安装的软件在启动时会
自动检测到新版本，提示后下载并静默安装，完成后自动重启。也可在「帮助 → 检查更新」手动检查。

## 数据
- 数据文件夹：首次运行时自行选择（建议放在 OneDrive）；数据库 `finance.db` 同时保存语言等设置。重装后启动软件，选回原文件夹即可恢复。菜单「文件 → 更改数据文件夹」可随时切换。
- 「文件 → 备份数据库」可导出备份文件。

## 本地运行（开发）
```
pip install -r requirements.txt
python run.py --no-update-check
```
