# CirClock 设计说明

> 工位节律闹钟 —— 不是番茄钟的复刻，而是「久坐上班族的身体节律调度器」。
> 本文档记录已锁定的设计决策，改动请同步更新此文件。

## 1. 定位

三层结构，决定这个软件是否有用：

| 层 | 内容 | 判据 |
|---|---|---|
| 计时层 | 队列、轮次、循环、暂停、跳过、结算 | 逻辑必须严丝合缝，不能吞时间 |
| 提醒层 | 何时提醒、如何升级、打扰到什么程度 | 太烦会被卸载，太弱会被无视 |
| 行为层 | 连续坐姿、离座确认、动作、打卡、统计 | 决定它是健康工具还是计时器 |

## 2. 已锁定的决策

| 项 | 决策 |
|---|---|
| 技术栈 | Python 3.12 + PySide6 (Qt 6.12)，环境在 `envs\.venv` |
| 默认主题 | **Fluent 浅色**（简约、跟随系统、圆角 8px） |
| 主题系统 | 主题包 = `themes/*.json`，可换主题、可改任意色值、可改字体/圆角/是否发光 |
| 自定义内容 | 阶段颜色、图标（emoji / 内置 SVG / 本地图片）、贴纸、铃声、文案全部进配置文件 |
| 提醒 | 默认**渐进式**：角落气泡 → 大卡片 →（可选）全屏置顶；声音、置顶、抢焦点均可勾选 |
| 健康模块 | 全选：动作库、连续坐姿计时+离座确认、饮水/如厕、护眼 20-20-20、统计与 CSV |
| 动作图示 | 内置一套自绘 SVG 简笔画（可直接选），支持用户自定义图片/emoji |
| 外部钩子 | 每个阶段可配「开始/结束时」执行：打开链接、打开文件、运行程序（可留空） |

## 3. 数据模型

```
Config
├─ settings            # 全局设置
└─ queues[]            # 多个队列，一个当前选中
    Queue
    ├─ name, id, description
    ├─ loop_mode        # count | forever | until（循环到某个时刻）
    ├─ loop_count       # count 模式下的轮数
    ├─ until_time       # until 模式的卡点，如 "18:30"
    ├─ entry[]          # 起始阶段，跑一次，可空
    ├─ rounds[]         # 轮次，每轮阶段可以不同
    │   Round
    │   └─ phases[]
    │       Phase
    │       ├─ name / kind(focus|move|stretch|eye|water|custom)
    │       ├─ minutes 或 区间 [min,max]（阶段开始时随机解析）
    │       ├─ color / icon / sound / message
    │       ├─ require_leave / allow_skip / pre_alert
    │       └─ hooks_start / hooks_end[]：{type: open|run, target, args, cwd}
    └─ exit[]           # 结束阶段，跑一次，可空
```

执行顺序固定为 `entry → (rounds 按 loop_mode 重复) → exit`。

**卡点是循环的终止条件，不是一个阶段。** 若把它做成阶段，无限循环永远走不到它；
做成条件后，每跑完一轮检查一次 `now >= until`，成立就转去 exit，否则继续下一轮。
开始队列时若该时刻已过，则跑完第一轮就收工，避免整夜空转。

番茄钟只是「1 轮 = 专注+短休，重复 4 次后接长休」的一个预设。

## 4. 状态机

```
idle ──start──> running ──pause──> paused ──resume──> running
                   │                  │
                   │ 时间到            │ skip
                   v                  v
                 alert ──ack(next)──> advance ──> (下一阶段 | 队列结束)
                   │
                   └─ snooze(n 分钟) ──> running
```

- 计时用 `time.monotonic()` + 绝对截止时刻，不用系统时间（防校时/夏令时）。
- 唤醒后若已过期，按「已过期」结算，不补跑。
- 阶段自然结束与用户跳过都写一条结算记录，`result` 区分 `completed` / `skipped`。
- 同一时刻只允许一个提醒窗，积压合并。

## 5. 模块划分

```
cirtimer/
  config.py      配置模型 + JSON 读写（便携模式：项目根目录放 portable.marker）
  engine.py      队列/计时状态机（纯逻辑，可单测）
  theme.py       主题包加载 + QSS 生成
  hooks.py       阶段开始/结束的外部动作（链接/文件/程序）
  audio.py       铃声播放（wav/mp3，循环到确认）
  stats.py       SQLite 事件记录 + 今日/趋势聚合 + CSV 导出
  autostart.py   HKCU Run 开机自启
  ui/
    main_window.py   侧栏 + 页面容器
    pages.py         计时 / 队列 / 统计 / 设置
    widgets.py       进度环、卡片、按钮
    alert.py         渐进式提醒窗（气泡→卡片→全屏）
    hud.py           角落迷你悬浮窗
    tray.py          托盘图标与菜单
tools/            音效合成、SVG 图示生成、UI 截图
themes/           主题包 JSON（用户可改可加）
assets/           内置图标、铃声
docs/             设计文档与风格稿
```

## 6. 里程碑

- **M1 能跑** ✅：配置、引擎、QSS 主题、主窗口+进度环、提醒窗、托盘、铃声、钩子、单实例。
- **M2 好用** ✅：队列编辑器（轮次/阶段增删、取色、图标、铃声试听、动作勾选、钩子编辑）、设置全量、时段计划、空闲检测、会议模式热键、勿扰、推迟次数上限。
- **M3 有用** ✅：动作库 19 个 + 自绘 SVG 简笔画、连续坐姿计时与久坐强提醒、离座确认、饮水/护眼独立提醒、统计与 CSV。

### 实现时补充/修正的决策

1. **单实例改用 `QLockFile`**：原先用 `QLocalServer` 命名管道，但在受限环境（沙箱）里命名管道被禁用，
   第二实例会卡死。改为 `%DATA%/.instance.lock` 文件锁；抢锁失败时用 `FindWindowW("CirClock")`
   把已有窗口叫到前面并退出。
2. **统计写入失败不能影响计时**：`stats.record_*` 吞掉 `sqlite3.Error`，`today_summary` 返回零值。
3. **数据目录回退**：`%APPDATA%\CirClock` 不可写时自动退到项目内 `data/`（沙箱/受限账户场景）。
4. **坐姿计时只在"人在"时累加**：空闲检测判定离开后暂停累加，回来重新计时。
5. **提醒不重建控件**：提醒窗、动作列表都用固定控件池 + 显隐，避免 `deleteLater` 未及时执行导致的重复渲染。
6. **Qt QSS 陷阱**：`border: none` 会让 `border-radius` 失效，主按钮因此加了一条同色 1px 边框。

## 7. 非目标

- 不做云同步、不做账号、不联网（除用户自己配的外链）。
- 不做医疗诊断或疗效承诺；动作库只写「活动建议」。
- 不接管锁屏/强制关机等系统级操作。
