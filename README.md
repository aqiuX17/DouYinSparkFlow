# DouYinSparkFlow：抖音续火花、AI 陪聊与微信 ClawBot 桥接

用自己的抖音账号运行，在电脑上管理登录和配置，在服务器上持续监听，通过微信查看消息、切换 AI／人工模式并回复好友或群聊。

本仓库是 [原项目](https://github.com/2061360308/DouYinSparkFlow) 的个人 fork。新增桥接功能在本仓库维护，不是抖音官方 API，也不是上游官方支持承诺。请只用于自己有权管理的账号及正常交流。

## 3.3.3：人工发送调度修复

- 人工回复队列现在会在每个会话扫描前，以及轮询休眠期间被处理，不再等完整扫描结束才发送。
- 浏览器操作仍在所属账号的同一个线程中执行；切换回扫描会话后再读取消息，避免把人工回复切换的聊天误当成扫描目标。
- 保留模式版本校验、过期取消、发送回执校验及“未确认不自动重发”规则；本次不是通过缩短回执校验来提速。
- 新增不含消息正文、账号或凭据的日志：`manual_send_timing queue_ms=... select_ms=... send_ms=... state=...`。三个耗时分别表示排队、选择聊天、发送并确认。
- 排查慢发送时区分“微信指令尚未被接收”“抖音发送排队”“浏览器发送确认”“微信回执通知排队”。本次只优化浏览器发送调度，不保证固定端到端时间。
- 更新后重启正在运行的陪聊进程才能使用新代码；仅下载源码或替换文件，不会更新已在运行的进程。升级前保留 `.env`、会话和绑定数据备份，不要将它们放入公开 ZIP。
- 本地六会话、2 秒轮询的虚拟时钟回归中，扫描期排队从 5.5 秒降到 0.5 秒，休眠期从 1.95 秒降到 0.1 秒。它们不是实际网络测速或性能承诺；线上耗时请看自己的日志。

## 新手先看这 5 件事

1. **需要正常登录抖音。**程序不会提供账号，也不会绕过登录。
2. **首次默认人工模式。**先配置 AI 服务和监听目标，再在 ClawBot 发送 `切换AI`；模式文件不存在或损坏时不自动回复。
3. **续火花不等于陪聊。**前者定时发消息，后者持续监听新消息，启动一个不等于启动另一个。
4. **Windows ZIP 必须完整解压。**不要在压缩软件中双击 EXE，也不要只复制 EXE；浏览器和 `_internal` 都是运行必需文件。
5. **配置就是凭据。**`.env`、Cookie、API Key、绑定文件、浏览器会话及聊天数据库不能上传公开仓库或发给陌生人。

## 目录

- [功能和限制](#功能和限制)
- [选择使用方式](#选择使用方式)
- [第一步：电脑配置账号](#第一步电脑配置账号)
- [第二步：Docker 服务器部署](#第二步docker-服务器部署)
- [第三步：扫码绑定和首次验收](#第三步扫码绑定和首次验收)
- [微信指令速查](#微信指令速查)
- [AI 回复时间与 60 秒规则](#ai-回复时间与-60-秒规则)
- [多账号使用](#多账号使用)
- [不用 Docker 的源码运行](#不用-docker-的源码运行)
- [更新、备份和回滚](#更新备份和回滚)
- [常见问题](#常见问题)
- [自己打包与测试](#自己打包与测试)
- [隐私与许可](#隐私与许可)

## 功能和限制

| 功能 | 说明 |
| --- | --- |
| 可视化配置 | 添加账号、正常登录、刷新凭据、选择续火花和陪聊目标 |
| 多账号续火花 | 多个账号依次执行，一轮任务不是并行发送 |
| 多账号 AI 陪聊 | 每账号独立浏览器线程；账号和会话的聊天上下文分开 |
| 多种 AI 服务 | DeepSeek、OpenAI 兼容接口；服务商、模型及 Key 由你配置 |
| 好友和群聊 | 监听选中的会话，群聊会回复新消息，不要求被 @ |
| 微信消息转发 | 新消息进入 SQLite 持久队列，再发给扫码绑定的微信用户 |
| 微信人工发送 | 获取编号后给指定好友／群聊发纯文本，无二次确认 |
| AI 回复可见 | ClawBot 收到 AI 正文及生成／发送状态，长回复分段通知 |
| 模式切换 | 所有账号共享 AI／人工模式，旧模式生成结果在发送前重新检查 |
| 登录状态保存 | 保存已有认证状态，减少重新登录；不会延长 Cookie 有效期 |

不自动添加好友、不自动加入群、不开放给任意微信用户、不保证永久登录或固定回复时间。表情和视频分享按可读标签／摘要处理，不代表识别图片或观看了视频；语音暂不支持。

微信侧使用 iLink 出站接口，抖音侧操作已登录聊天网页。无需服务器上的微信桌面客户端，也不需要公网 Webhook。**无公网端口指 `docker-compose.chat.yml` 桥接方案，不包括续火花 Compose 中的 gost 代理端口。**

```text
抖音已监听会话的新消息 → 浏览器读取 → 持久队列 → 微信 ClawBot
微信模式指令／人工回复 → 校验绑定用户 → 指令或发送队列 → 抖音浏览器
AI 生成正文与发送状态  → 持久通知队列 → 微信 ClawBot
```

## 选择使用方式

| 需求 | 使用入口 | 运行要求 |
| --- | --- | --- |
| 登录、配置账号 | Windows 发行包或 `python main.py app` | 需要图形桌面 |
| 每天定时续火花 | 应用定时设置或 `docker-compose.yml` | 按定时／开机模式执行 |
| 服务器持续陪聊及微信桥接 | **`docker-compose.chat.yml`** | chat 和 weixin 都持续运行 |
| Linux 源码部署 | `python main.py chat` 和微信 worker | 两个进程持续运行 |

新手推荐：**Windows 配置 → 私密传配置到 Linux amd64 服务器 → Docker 启动 → 微信管理**。

下载：[本仓库 Releases](https://github.com/aqiuX17/DouYinSparkFlow/releases)。只选择有实际资产的版本；Release 页面存在不代表全部平台构建成功。源码 ZIP 不是可双击运行的 Windows 包。

## 第一步：电脑配置账号

### 1. 打开程序

Windows 下载 `DouyinSparkFlow-*-win-x64.zip`（旧包可能没有版本号），完整解压到可写目录，例如 `D:\DouyinSparkFlow`，双击 `DouyinSparkFlow.exe`。

```text
DouyinSparkFlow/
  DouyinSparkFlow.exe
  _internal/
  cloakbrowser-windows-x64/
  gost/
  README.md
  .env.example
```

首次没有真实 `.env` 是正常的。示例 `your-sessionid` 和空 API Key 不是有效凭据。Windows 包用于桌面管理，不是 Linux 服务器程序。

### 2. 登录与选目标

1. 进入“账户配置”，点击“添加账号”。
2. 在打开的浏览器中完成正常登录，等待账号信息获取完成。
3. 拉取会话列表，确认是自己的账号和目标。
4. 多账号重复添加；登录失效时使用“刷新登录”。
5. 在“AI 陪聊”的“陪聊好友与群聊”中选择监听目标。

陪聊名单和续火花名单独立。不要一开始就选择很多群，先用一个有权测试的好友验证。重名时使用会话 ID，好友也可使用抖音号或 UID。

### 3. 配置模型服务

在“AI 陪聊”填写服务类型、API 地址、模型名称和 API Key，点击“测试 API”。以服务商实际支持的模型为准；仓库默认模型名只是配置默认值。

API 测试只验证模型请求，不验证抖音登录或微信转发。改变配置后停止并重新启动陪聊，因为运行进程使用启动时的快照。

### 4. 保存并迁移配置

源码 `.env` 位于仓库根目录；Windows 包默认位于 EXE 所在目录（`APP_DATA_DIR` 可改变数据位置）。这是含真实凭据的完整配置。

将它通过可信方式传到服务器的 `config/.env`。不要用已隐藏 Key 的“概览／复制配置”替代完整迁移文件，否则服务器可能缺密钥。异地出口可能触发登录检查，仍需正常刷新登录，不保证复制凭据就永久可用。

## 第二步：Docker 服务器部署

以下命令在 **Linux 服务器终端**运行，不是在微信里运行。先安装 Docker Engine、Compose v2，确认 `docker compose version` 可以执行。当前 Dockerfile 内置 x64 Chromium，面向 Linux amd64，不保证 ARM64 可用。

### 1. 下载代码并准备私有配置

```sh
git clone https://github.com/aqiuX17/DouYinSparkFlow.git
cd DouYinSparkFlow
install -d -m 700 config config/sessions .weixin-bridge
```

放入电脑生成的真实 `config/.env` 后，检查：

```sh
test -f config/.env && echo '配置已找到'
chmod 600 config/.env
```

找不到文件时先检查路径和隐藏扩展名，避免把 `.env` 保存为 `.env.txt`。不要使用示例假 Cookie 继续部署。

### 2. 构建常驻镜像

```sh
docker compose -f docker-compose.chat.yml build chat
```

会下载依赖和 Chromium，耗时取决于网络。**构建成功再继续。**本机构建不依赖 GitHub Actions，但依然需要正常访问下载源。

两个服务共用同一镜像：chat 负责抖音监听、模型和人工发送；weixin 负责微信收发。只有一个进程时链路不完整。

## 第三步：扫码绑定和首次验收

### 1. 绑定自己的微信

手机先启用可用的 ClawBot 接入，再在服务器运行：

```sh
docker compose -f docker-compose.chat.yml run --rm --no-deps \
  --entrypoint python weixin -m core.ai.weixin_bind
```

出现 `QR_READY` 后，宿主机 `.weixin-bridge/qr.json` 保存私有扫码入口。脚本**不会自动画出二维码**；在可信本地环境查看 `qrcode_img_content`，用自己的微信打开／扫码。不要把文件或入口上传公共二维码网站。

出现 `BINDING_SAVED_PRIVATE`，且私有目录中生成 `binding.json`，才表示绑定凭据已保存。二维码过期时重跑命令；已有有效绑定不必每次重扫。

### 2. 启动并先向机器人说句话

```sh
docker compose -f docker-compose.chat.yml up -d chat weixin
docker compose -f docker-compose.chat.yml ps
docker compose -f docker-compose.chat.yml logs --tail=100 -f
```

在微信 ClawBot **先发一句话**，更新回复所需的 `context_token`，再发 `查看模式` 和 `获取聊天列表`。首次默认人工模式。

### 3. 逐步确认真实收发

1. 等待日志显示监听完成，微信能查询聊天编号。
2. 让已配置测试好友发一条新抖音消息，在手机核对转发。
3. 发 `切换人工`，再发 `发送 3 测试收到`，把 3 换成实际编号。
4. 同时核对微信状态和抖音会话，不把“已排队”当成“已送达”。
5. 发 `切换AI`，让测试好友再发新消息。
6. 核对 AI 正文、发送状态和抖音实际回复。

容器 running、服务 active 不是收发验收。出现在聊天列表里的会话也不等于已加入监听。

## 微信指令速查

下面文字发到 **ClawBot 对话**，不是服务器终端。只接受扫码绑定用户的指令。

| 指令 | 用途 | 边界 |
| --- | --- | --- |
| `查看模式` | 查询 AI／人工模式 | 不负责启动浏览器 |
| `切换AI` | 开启自动回复 | 作用于全部账号；需已有服务和监听配置 |
| `切换人工` | 停止自动回复，保留转发和手动发送 | 不撤回已发消息 |
| `获取聊天列表` | 查询会话编号及名称 | 是启动扫描目录，不是监听名单 |
| `发送 3 你好` | 向编号 3 发送“你好” | 仅人工模式、无二次确认；先核对编号 |
| `查看回复目标` | 查看快捷目标和剩余时间 | 没有有效目标时用编号 |
| `帮助` / `发送帮助` | 查看发送规则 | 不会当作好友消息发送 |

别名：`人工模式`、`切换ai`、`AI模式`、`聊天列表`、`获取好友列表`。模式命令支持空格、AI 大小写、全角字符和前面的 `/`。疑似错写模式命令会明确拒绝，**不会直接发给好友**。确实想给好友发这类文字，请用 `发送 编号 内容`。

人工发送内容最长 1500 字；旧的 `确认发送 ...` 不再执行二次确认。

AI 正文自动通知，无需额外指令，分为：

- **已生成（尚未发送）**：只是模型结果，不代表抖音已发。
- **抖音发送回执已确认**：回执成功，不代表对方已读。
- **未发送**：模式改变或消息已过时。
- **发送未确认**：先核对抖音，不自动重发。

AI 通知不改变人工快捷目标；长回复分段。通知入队不等于手机已收到，仍依赖有效上下文、微信接口和网络。

## AI 回复时间与 60 秒规则

### AI 多久回复？

**不等待 60 秒。**默认每轮检查结束后等待 5 秒；同一会话两次成功 AI 回复至少间隔 15 秒，首条合格新消息不必先等 15 秒。还要加上会话切换、模型生成和发送时间，不保证固定几秒内回复。会话多时，一轮扫描更久。

默认请求超时 30 秒；模型生成失败退避 60 秒再试，不是正常消息都等 60 秒。实际值以 `AI_CHAT` 配置为准。

生成期间又有新消息或你已在抖音手动回复，旧结果会被丢弃并重新判断。启动时跳过现有历史消息。切回 AI 不补发人工期间已处理消息，尚未处理的消息可能在下一轮由 AI 回复。

### 人工 60 秒快捷回复

只有人工模式下，抖音新通知成功提交微信后 60 秒内，ClawBot 普通文字才会发往**最近通知的会话**：

```text
A 的新消息通知 → 输入“收到” → 回复 A
B 的新消息通知 → 输入“收到” → 此时回复 B
超过 60 秒     → 不直接发送，改用“发送 编号 内容”
```

计时从接口返回成功消息 ID 开始，不是手机打开通知的时间，也不是送达证明。新通知改变目标，已经排队的回复目标不会变。多账号共享这个目标，不确定时用编号。

### AI 回复后，还能人工补充吗？

AI 模式下普通文字和编号发送都不会转发到抖音，60 秒内也一样。先切换人工，再指定编号：

```text
切换人工
发送 3 我的补充说明
```

真正切换模式会使旧快捷目标失效；切换后不要依赖上一条通知直接回复。重复切换同一模式不刷新版本或清空目标。模式切换不撤回已发／已经进入浏览器发送动作的消息，需要核对结果。

## 多账号使用

推荐在应用逐个登录保存。结构示意（不是有效登录配置）：

```dotenv
TASKS=[{"username":"账号一","unique_id":"dy_one","targets":["续火花好友"],"ai_targets":["陪聊好友"]},{"username":"账号二","unique_id":"dy_two","targets":[],"ai_targets":["测试群"]}]
COOKIES_DY_ONE=[{"name":"sessionid","value":"REPLACE_WITH_YOUR_COOKIE","domain":".douyin.com","path":"/"}]
COOKIES_DY_TWO=[{"name":"sessionid","value":"REPLACE_WITH_YOUR_COOKIE","domain":".douyin.com","path":"/"}]
```

JSON 必须单行。Cookie 键后缀是抖音号大写，避免 ID 冲突。上面没有完整可登录 Cookie 或 AI 配置。

账号 Cookie、指纹、浏览器上下文和陪聊上下文分别隔离；**AI 服务设置、续火花时间／模板、AI／人工模式及微信快捷目标仍为全局共享**。不是每个账号独立绑定微信、独立切换模式。

## 不用 Docker 的源码运行

进阶方案建议 Python 3.12；还需平台对应的 CloakBrowser 二进制和操作系统浏览器运行库。可视化配置需要图形桌面，没有桌面的服务器应先在电脑配置。

```sh
git clone https://github.com/aqiuX17/DouYinSparkFlow.git
cd DouYinSparkFlow
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
# 需要可视化界面时，另安装 Node.js／npm 并构建前端
cd app/web/ui && npm ci && npm run build && cd ../../..
```

Git 仓库不包含浏览器本体。获取资源和路径见 [源码部署](docs/deploy/source.md) 与 [打包工作流](https://github.com/aqiuX17/DouYinSparkFlow/blob/main/.github/workflows/build-app.yml)，不要认为装好 pip 依赖就具备全部运行条件。

下面三个变量必须同时传给绑定、chat、worker，路径使用自己的可写目录：

```sh
install -d -m 700 "$HOME/.local/share/douyin-bridge"
export DOUYIN_WEIXIN_STATE_DIR="$HOME/.local/share/douyin-bridge"
export DOUYIN_WEIXIN_DB="$DOUYIN_WEIXIN_STATE_DIR/forward.sqlite3"
export DOUYIN_REPLY_MODE_FILE="$DOUYIN_WEIXIN_STATE_DIR/reply-mode.json"
python -m core.ai.weixin_bind
# 绑定后在两个终端分别运行，各终端都设置变量并激活虚拟环境
python main.py chat
# 另一终端：python -m core.ai.weixin_worker
```

systemd 模板见 `deploy/douyin-weixin-forward.service`，必须调整 User、WorkingDirectory、ExecStart、EnvironmentFile，并另行管理 chat；只安装 worker 服务不会自动启动抖音监听。见 [微信桥接部署指南](docs/guide/微信桥接.md)。

不接微信而单独用源码 AI 时，可以在共享同一模式路径的终端执行 `python -c "from core.ai.reply_mode import set_mode; set_mode('ai')"`。这是源码命令，不表示 Windows EXE 支持任意 Python `-m` 操作。

## 更新备份和回滚

更新前停止相关进程，备份私有配置、绑定、模式、会话和 SQLite。不要把正在写入的数据库直接复制当成可靠备份；数据库回滚与代码回滚应分别评估。

Docker 源码构建部署的更新顺序：

```sh
docker compose -f docker-compose.chat.yml stop chat weixin
# 已备份、确认没有未提交本地改动之后：
git pull --ff-only
docker compose -f docker-compose.chat.yml build chat
docker compose -f docker-compose.chat.yml up -d chat weixin
docker compose -f docker-compose.chat.yml logs --tail=100 -f
```

构建失败不要使用不确定的新镜像继续启动，保留原镜像与备份排查。不要随意删除私有目录或执行 `down -v`。更新后重新核对模式、监听、手机转发与编号发送；已有有效绑定通常无需重扫。

使用 GHCR 发布镜像时，先确认 [Docker Actions](https://github.com/aqiuX17/DouYinSparkFlow/actions/workflows/docker-publish.yml) 成功及实际镜像存在，再设置 `DOUYIN_IMAGE` 并 pull。main 有提交不代表 latest 镜像已更新。

## 常见问题

| 现象 | 排查方向 |
| --- | --- |
| EXE 打不开／缺文件 | 完整解压、保留运行目录、可写路径；不要盲目关闭安全软件 |
| 找不到前端 | 源码构建 `npm ci && npm run build`；发行包检查完整性 |
| 有 Cookie 但登录失效 | 刷新登录、账号及出口；状态保存不延长有效期 |
| AI 不回复 | 查询模式、确认监听目标和 API、检查是否历史消息／冷却中 |
| 模式指令被当成聊天 | 更新 chat 与 weixin 两端，核查运行代码／镜像版本 |
| 微信无转发 | 绑定、首次发话、worker、context_token、网络和接口错误 |
| 有微信回执但抖音没发 | chat 是否运行、登录／会话是否有效、明确发送结果 |
| 普通文字不转发 | 是否人工、60 秒是否已过、刚切换模式是否失效了旧目标 |
| 名称重复 | 用会话 ID；好友也可用抖音号／UID |
| 担心发错人 | 查询回复目标，更稳妥的是指定会话编号 |
| 显示生成但没发 | 查看后续取消／未确认，生成不是发送成功 |
| uncertain | 先核对真实聊天，不盲目重发 |
| Actions 没有包 | 看具体 job 日志；账户账单锁定曾导致构建不能启动，需所有者处理账户 |

排查只分享脱敏错误，不发完整凭据或聊天数据库。

## 自己打包与测试

### Windows 本机打包

`tools/packaging/windows/build.ps1` 复用既有前端及 PyInstaller 布局。需要 Windows x64、Python、Node.js／npm；在仓库根目录运行：

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
.\tools\packaging\windows\build.ps1 -Python python -OutputRoot C:\build\douyin
```

输出目录必须不存在。脚本构建前端，下载浏览器及 gost（也可传入现有二进制路径），生成 EXE，带上文档、许可和示例配置，压缩 ZIP。不要直接压缩日常运行目录，避免真实 Cookie、会话和聊天记录混入。

### GitHub 构建

[Build app](https://github.com/aqiuX17/DouYinSparkFlow/actions/workflows/build-app.yml) 可手动触发，或推送 `v*` tag；以 job 成功及 Release 实际资产为准。本地 Windows 包完成不等于 Linux deb 和 Docker 镜像已经完成。

### 隔离测试

不要使用生产数据库。Linux 示例：

```sh
T=$(mktemp -d)
export DOUYIN_WEIXIN_DB="$T/queue.sqlite3"
export DOUYIN_REPLY_MODE_FILE="$T/mode.json"
export DOUYIN_SESSION_DIR="$T/sessions"
python -c "from core.ai.reply_mode import set_mode; set_mode('ai')"
python -m unittest tests.test_session_store tests.test_ai_chat tests.test_bridge_mode_commands
python tests/check_weixin_bridge.py
```

包含模拟浏览器／模型，不能替代真实手机及生产验收。测试后只清理新建临时目录，不要误删生产状态。

## 隐私与许可

- Linux 私有目录建议 700、敏感文件 600；妥善保护扫码、API、登录和聊天数据。
- AI 会把所选会话的可读消息发给你的模型服务；正文通知保存到队列并发给绑定微信。
- 队列没有自动清理策略，需自行制定保留期；不要公开数据库。
- 免确认发送有误发风险，未知结果先人工核对。
- 接口、登录、网络和平台规则可能变化，不承诺永久可用。
- 仅用于学习、个人自用和正常交流，不用于骚扰、刷量或规避平台限制。

保留上游版权与 [MIT LICENSE](LICENSE)。作者和原功能见 [原项目说明](docs/guide/原项目说明.md)，微信接入参考 [Tencent/openclaw-weixin](https://github.com/Tencent/openclaw-weixin)。
