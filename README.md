# 不背单词复习助手（bbdc-to-ai）

把自己在「不背单词」里学过的词整理成一份每日复习 Markdown。它根据已保存的学习记录筛出答错或拿不准的词，附上中文释义和分类依据，并自动生成词根联想、记忆钩子和考研长难句拆解的提示词。你可以把文件复制给自己常用的 AI，也可以存到 Obsidian。

- **同步学习记录**：在 Windows 助手里点击「查看已有复习」，打开 MuMu 里的不背单词同步，再刷新词表。
- **专注薄弱词**：熟词只计数。同一个词在多天反复模糊或答错时，会优先进入顽固词表。
- **离线导出和预览**：用电脑上已保存的记录生成 Markdown，在窗口里预览、一键复制，或另选保存位置。

项目面向使用 Windows 和 MuMu 学英语的用户。学习记录在本机处理，AI 提示词由你自行复制发送。查看 [合成示例](examples/synthetic_review.md) 可以了解最终文件的样子。

## 下载 Windows 版

在 [GitHub Releases](https://github.com/zhitai0529/bbdc-to-ai/releases) 下载 `bbdc-to-ai-windows-x64.exe`，双击即可打开。EXE 自带 Python 运行环境。

从 App 同步需要 Windows x64、可用的 MuMu 和已登录的不背单词。设备读取目前只验证了 **MuMu Android 15、不背单词 5.11.8 x86**，需要该 MuMu 实例已启用 root 和 ADB。EXE 不包含模拟器或 APK。已有本机记录时，可以直接离线导出。

## 每天怎么用

1. 双击 EXE。助手窗口会显示保存位置，并预览最近一次本地导出。
2. 在窗口里点 **「查看已有复习」**，助手才会打开 MuMu 和不背单词。它会通过「头像 → 学习偏好 → 更多学习偏好 → 同步学习数据」发起同步，并在 App 提示成功后刷新最近有记录的学习日。
3. 窗口显示复习内容后，点 **「复制全部内容」**，到 AI 聊天窗口按 `Ctrl+V` 粘贴并发送。

想重新查看上次导出的内容，可以点 **「仅看本地文件」**。同步未完成时，助手也会说明原因并尝试打开已有文件。

想换到其他文件夹，点 **「更改保存位置」** 并选中目标文件夹。助手会记住选择，以后把复习文件导出到这里。之前导出的文件仍在原文件夹。点 **「打开保存位置」** 可以在资源管理器里打开当前目录。如果实时抓包窗口已经在运行，重新打开它即可加载新的保存位置。

「导出今日复习」只用电脑上已保存的今日记录生成文件，可以离线使用。刚学的单词需要先同步到电脑，点「查看已有复习」即可同步并更新词表。

同步或导出期间，点窗口右上角的 **×** 可以关闭助手并停止后台任务。取消同步时，助手会关闭本次同步由它启动的 MuMu 实例。

EXE 首次运行会在 `%LOCALAPPDATA%\bbdc-to-ai` 创建独立配置和缓存。要使用之前源码版的 Markdown，点「更改保存位置」选择原来的目录。

## 从源码运行

源码版需要 Python 3.10+。在项目目录双击 `setup.bat` 安装依赖，再运行：

```powershell
.\.venv\Scripts\python.exe -m src.desktop
```

`export_daily.bat` 是离线导出的命令行入口。`config.example.yaml` 是初次运行生成本地配置用的模板。

设备同步入口通过 adb root 读取学习库的稳定副本。找到目标日期的词条后才读取词典，并批量查询释义。SQLCipher 逐页验证 HMAC，解密后的 SQLite 再做完整性检查，临时明文数据库用完关闭并删除。数据库仍在写入时，请完成本组学习后重试。

App 的学习日按本地**凌晨 04:00**切换。「导出今日复习」和 `export_daily.bat` 默认只导出当前学习日。「查看已有复习」同步后选择最近有记录的学习日。

```powershell
# 当前学习日无记录时导出最近学习日
.\.venv\Scripts\python.exe -m src.mumu --latest
# 指定学习日
.\.venv\Scripts\python.exe -m src.mumu --date 2026-11-11
# 严格只导出当前学习日，无记录则报告失败
.\.venv\Scripts\python.exe -m src.mumu
```

自动发现 MuMu 安装位置和唯一在线 ADB 设备；多个实例时可用 `--adb` 和 `--serial` 指定。自动适配仅支持已核对的 5.11.8 x86 native 库，App 更新导致哈希变化时会停止，不能假定新版本协议相同。

在 WSA 上试用时，在 WSA 设置里查看开发人员模式显示的 ADB 地址。WSA 需已安装兼容版本并保存学习记录。若使用带 Magisk 的 WSA，需由用户在 WSA 中授权 Shell，导出程序通过 `su` 读取学习库。

```powershell
.\.venv\Scripts\python.exe -m src.mumu --serial 127.0.0.1:58526
```

## 实时抓包

实时抓包是源码版的独立入口。双击 `run_sniffer.bat`。默认 `mode: auto`，端口 8888，绑定 127.0.0.1。启动器会：

- 启动 mitmdump，使用项目自己的 `.local_setup/mitmproxy` CA。
- 对本机 Android 15 临时挂载含 CA 的信任目录，配置 ADB reverse 和模拟器代理。
- 备份 `bbdc.cn`、`beingfine.cn` 及其子域名的 `application/json` 响应，解开已适配的 V3 正文；识别词条后合并、导出并显示 Rich 统计表。
- 对已成功响应的 `/v3/bb/user-stat/process/...`，还读取 POST 的 `stat` 学习记录；不备份请求中的认证参数。

保持窗口运行，再在 App 中完成自己的学习和正常同步。**按 Ctrl+C 退出**，恢复原网络代理、移除本次 ADB 转发与证书挂载。若抓包窗口意外退出后 MuMu 连不上网，请保持模拟器开启并双击 `restore_mumu_network.bat`。新版恢复脚本也可识别旧版留下的代理地址。

首次使用实时抓包前，在助手里点一次「查看已有复习」，或从正在运行的模拟器执行 `python -m src.mumu`，初始化本地协议与释义缓存。原始接口缺中文释义时，流水线从该缓存补充。

只想采样时设置 `mode: sniffer`；保留原始 JSON，不自动生成 Markdown。不会改变 App 的响应或替用户点击答题。

## 字段和分类含义

真实格式使用专用适配器 `src/bbdc_schema.py`：

| 字段 | 已核对含义 |
| --- | --- |
| `wd` / `wi` | 拼写 / 单词 ID |
| `st` | 学习状态；仅选取已学/复习/已标熟状态 3、4、9，排除下载未学词 |
| `ut` | 当前记录更新时间，用于匹配复习学习日 |
| `lt` | 首次学习时间，不用它确定后续复习日期 |
| `rh` | 历次复习评分，取最近一组的最后一项；A 最好 |
| `ah` | 答题历史，取最近一组的最后一项 |
| `meaning` | 本地词典按单词 ID/拼写关联得到的中文释义 |

已核对组合：A/0 → 本轮直接认识，剔除；B/110 → 模糊；D/E/F 配合 210/410/610/810 → 顽固，对应本轮确认的 1/2/3/4 次错误。初学完成的单数字 `rh` 等于 `ah` 时，数字代表初学答错次数（9 是封顶值）。初学答错词进顽固组，初学零错词计入剔除数。App 手工标熟状态按已核对条件处理。其余组合按「复习不会」纳入顽固词，错误次数默认记 1 次。

**本轮直接认识不等于永久掌握；本轮错误数不等于全天或历史累计错误。** 数据库快照保留最近状态；同词多个同步包以较新时间的记录为准，不累计重复快照。它不能恢复已经被后续复习覆盖的全天逐次按钮历史，也不能保证用户每天一定有 150～200 条记录。当前记录实际有多少就导出多少。

真实格式中的 `level` 常为 0，不能据此推断熟练度。`config.yaml` 的 `parser` 阈值与字段映射用于其它通用 JSON；它们不会覆盖已验证的专用 rh/ah 解释。

## 核对未知编码和跨天提级

未确认 Android 编码的词会直接进主复习文件。默认省略单独的编码核对报告，重新导出时会清理同一目录、同一学习日的旧报告。需要核对时，在 `config.yaml` 设置 `write_unknown_codes_report: true`，再次导出后就可以通过「打开保存位置」找到 `YYYY-MM-DD_unknown_codes.md`。报告按当天去重后的词数降序排列，每组最多列 5 个例词和已有的中文释义。表里的 `ah` 是最近一轮的末项，`rh` 是最近一组的评分串，「复习评分」是该评分串的末项。

在 App 核对后，打开同目录的 `rules.yaml`，在 `code_rules` 列表末尾复制一条规则并改为已确认的 `ah`、`ratings`、`category` 和 `recognition`。若只对报告里的某个评分串成立，再填写带引号的 `rh`，这类规则优先匹配。错误数不确定时省略 `wrong_count`。保存后重新导出该日即可应用，长期开着的抓包窗口需要重启。当天所有编码都识别后，旧报告会被移除。旧缓存如果缺少完整评分组，重放对应原始包即可补齐。

首次成功导出会创建项目里的 `data/history.db`。每个学习日每词保留一条提级前的分类。不区分词的大小写。同一天再次导出会更新对应记录。默认统计当天及前 6 天，曾被归为模糊或顽固的学习日达到 2 天，就把当天仍模糊的词移进顽固组。可在 `config.yaml` 调整 `escalation_window_days` 和 `fuzzy_escalation_threshold`。历史从新版成功导出开始积累。想加入已有快照，可以用原来的命令逐日重放，并按从早到晚的顺序处理。映射变化影响本次导出，已存的历史日期可以通过重放更新。

## 配置、样本和离线重放

`config.yaml` 可修改 `listen_port`、`output_dir`、`raw_dump_dir` 和 `state_dir`。输出到 Obsidian 时例如：

```yaml
output_dir: 'D:/Obsidian/英语复习'
```

相对路径相对于配置文件目录。每日缓存按拼写去重，文件锁与原子写入防止并发损坏。同日继续导出会更新同一 Markdown；分类配置变化时拒绝混用旧缓存，可指定新的 `state_dir` 后重放原始包。

```powershell
# 仅查看字段结构，不打印值
.\.venv\Scripts\python.exe -m src.cli inspect .\sample_response.json
# 将指定原始包重放到指定学习日
.\.venv\Scripts\python.exe -m src.cli replay .\raw_dumps\你的快照文件.json --date 2026-11-11
```

备份文件名含时间、接口路径和随机后缀，不含 URL 查询参数。未适配的 V1 加密包会提示并保留原件，不会冒充空词表。整目录重放若包含这类不支持的包，会逐项报告失败并继续其它包。

`config.yaml`、原始响应、缓存、导出和历史库只保存在本机。原始响应可能含账号信息、token 或安全参数。发行版和测试只使用默认配置及合成样本。

## 测试与模块

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用合成数据和临时输出，覆盖字段分类、凌晨 4 点的日期边界、历史提级、去重、离线导出、同步取消和代理恢复。

- `src/interceptor.py` / `envelope.py`：代理采集、应用层解密。
- `src/parser.py` / `bbdc_schema.py`：通用映射、实际版本适配。
- `src/mumu_adb.py` / `mumu_snapshot.py` / `localdb.py`：设备连接、只读副本、释义查询与数据库校验。
- `src/mumu.py` / `offline_export.py`：分别处理设备读取和本机离线导出。
- `src/desktop.py` / `desktop_view.py` / `desktop_files.py` / `desktop_worker.py`：分别处理窗口操作、界面布局、保存位置与文件查找、后台任务。
- `src/pipeline.py` / `review_cache.py` / `storage.py`：组织导出、按学习日维护缓存、原子写文件。
- `src/history.py`：SQLite 每日记录和跨天统计。
- `src/exporter.py`：Markdown AI 提示词与未知编码核对报告。
- `src/launcher.py` / `emulator_proxy.py`：代理进程、临时 CA 与网络恢复。
- `src/cli.py`：字段检查与离线重放。

`tests/fixtures/synthetic_response.json` 和 `examples/synthetic_review.md` 均为合成示例，不是你的学习记录。

## 版本和构建

功能更新和修复保存在 Git 提交记录，公开版本见 [CHANGELOG.md](CHANGELOG.md)。推送 `v*` 标签会触发 Windows 测试、构建和 GitHub 发布。

```powershell
python -m pip install -r requirements.txt -r requirements-build.txt
.\packaging\build_windows.ps1 -Python python
python -m tests.smoke_windows dist/bbdc-to-ai.exe
```
