# DouYinSparkFlow · 服务器 AI 陪聊与微信 ClawBot 双向桥接

本仓库是 [2061360308/DouYinSparkFlow](https://github.com/2061360308/DouYinSparkFlow) 的个人 fork，保留原项目的可视化管理、自动续火花、多账户和 Docker 功能，并增加 AI 陪聊、会话状态保存及微信 ClawBot 双向消息桥接。修改维护在本仓库；不是上游官方功能。

## 核心：在服务器运行，通过微信管理抖音聊天

**支持 Linux 服务器长期部署、AI 陪聊，以及微信 ClawBot 与抖音的双向消息桥接。** 无需在服务器运行微信桌面客户端；抖音侧使用已登录的无头浏览器，微信侧使用 iLink 出站接口。可以源码 + systemd 常驻运行，也可用同一 Docker 镜像启动独立的 chat 和 weixin 两个容器。

## 微信 ClawBot ↔ 抖音：原理与方法

```text
抖音好友／群聊新消息
  → 已登录浏览器读取（只扫描配置的监听目标）
  → SQLite 持久化出站队列与去重
  → iLink sendmessage（绑定用户 + context_token）
  → 手机微信 ClawBot

手机微信 ClawBot 指令／回复
  → iLink getupdates 长轮询（校验绑定的 from_user_id）
  → 解析模式、编号或 60 秒最近会话路由
  → SQLite 发送队列（冻结目标 conv_id）
  → 原浏览器线程选择会话并发送
  → 发送状态通过微信返回
```

微信侧通过 `ilinkai.weixin.qq.com` 的 `getupdates` 收消息、`sendmessage` 发消息；抖音侧不是官方私信开放 API，而是 `DouyinIM` 操作已登录聊天网页。两个进程共享私有数据库和模式文件，浏览器操作仅在其拥有者线程执行；没有公网 Webhook、没有入站端口，也不依赖 Grok。手机扫码绑定后必须先向 ClawBot 发一句话，获得回复必需的 `context_token`。

**接入顺序：** 配置抖音账号、AI 服务和监听目标 → 建立私有状态目录 → 手机启用 ClawBot 并扫码 → 启动 chat 和 weixin → 在 ClawBot 发一句话 → 获取聊天列表／切换模式／发送测试。完整命令见 [微信桥接部署指南](docs/guide/微信桥接.md)。

## 功能

- 抖音已监听会话的新消息转发到绑定的微信账号；只接收该绑定人的微信指令。
- 微信获取抖音聊天列表，按编号给好友或群聊发送纯文本，无二次确认。
- 人工模式下，新消息成功提交微信接口后的 60 秒内，普通微信文字默认回复最近一次通知对应的抖音会话。
- 微信切换 AI／人工模式，切换后丢弃旧模式生成中的回复，避免旧任务误发。
- SQLite 持久化队列和去重；未知发送结果标记 uncertain，不自动重发。
- iLink 长轮询收消息、出站 POST 发消息；桥接程序不开放公网端口，不依赖 Grok routine 或 Webhook。

## 快速开始

源码部署建议使用 Python 3.12（服务器验证版本）；浏览器需具备运行依赖。

```sh
git clone https://github.com/aqiuX17/DouYinSparkFlow.git
cd DouYinSparkFlow
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py app
```

先在应用中配置抖音登录、AI 服务和监听目标，再运行 `python main.py chat`。微信桥接部署与扫码绑定见 [微信桥接指南](docs/guide/微信桥接.md)；AI 参数见 [AI 陪聊](docs/guide/AI陪聊.md)。原功能、界面及上游教程见 [原项目说明](docs/guide/原项目说明.md)。

> 此版本默认人工模式：模式文件不存在或损坏时不自动回复。启用 AI 需要发送“切换AI”或显式调用模式配置。人工模式仍需要现有 chat 配置和浏览器监听进程。

## 服务器部署与 AI 陪聊

- **源码 + systemd：** `.venv/bin/python main.py chat` 持续监听；`.venv/bin/python -m core.ai.weixin_worker` 接入微信。适合现有 Linux 服务器，不必迁移正在运行的服务到 Docker。
- **Docker 常驻：** 使用新增 `docker-compose.chat.yml`；`LAUNCH_MODE=chat` 运行 AI／人工监听，`LAUNCH_MODE=weixin` 运行微信桥接。原 `docker-compose.yml` 仍是 cron 续火花，不是持续陪聊。
- **AI 服务：** 支持 DeepSeek、OpenAI 兼容接口、多轮上下文、角色提示词与群聊成员区分；在应用中配置 `AI_CHAT` 和账号的 `ai_targets`。密钥仅保存在私有 `.env`。
- **人工／AI 切换：** 默认人工。微信“切换AI”启用已配置目标的自动回复，“切换人工”停用自动回复但保留新消息转发与手动发送。模型缺失或配置未启用，不会因为发一条切换指令就自动完成配置。

```sh
# 先按部署指南准备 config/.env、私有目录和扫码绑定
# 使用本机 Docker 构建，不依赖 GitHub Actions
# 默认关闭专有 Windows 字体；只支持当前预置的 linux/amd64 浏览器
docker compose -f docker-compose.chat.yml build chat
docker compose -f docker-compose.chat.yml up -d chat weixin
docker compose -f docker-compose.chat.yml logs --tail=100 -f
```

镜像发布至本仓库对应的 `ghcr.io/aqiux17/douyinsparkflow`；以 Actions 成功状态及实际镜像摘要为准，不表示最新提交已经发布。[服务器部署、扫码和运行检查](docs/guide/微信桥接.md#docker-服务器常驻部署)。

## 微信指令

| 指令 | 用途 |
| --- | --- |
| 获取聊天列表 | 显示编号、好友／群聊及名称 |
| 发送 3 你好 | 人工模式下直接发送到编号 3，不再确认 |
| 查看回复目标 | 查看当前快捷回复目标与剩余时间 |
| 切换人工 / 人工模式 | 停止 AI 自动回复，保留转发和手动发送 |
| 切换AI / AI模式 | 启用已配置目标的 AI 自动回复 |
| 查看模式 | 查看当前全局模式 |
| 帮助 / 发送帮助 | 查看发送规则 |

### 60 秒规则与边界

A 的通知后直接回复发给 A；如果 B 的新通知随后成功发送，默认目标立即切换为 B。已入队的回复目标冻结，不会改投 B。超时后普通文字不发送，请用“发送 编号 内容”。计时从服务端 iLink 返回成功消息 ID 开始，不是手机打开通知的时间，也不是手机送达证明。模式切换会使旧快捷回复目标失效。

聊天列表是启动扫描的会话目录，**不等于好友通讯录，也不等于全部监听**；新消息仅监控配置中的目标，新增会话需重新扫描。模式及快捷回复目标当前为单一绑定人的全局状态，多账户使用也共享最新目标。群聊有直接发送权限，但最新群聊／快捷回复组合目前只有模拟浏览器测试，尚不能宣称实机群聊发送验收完成。

## 测试与源码

```sh
python tests/check_weixin_bridge.py
# 标准测试需要隔离模式、队列和会话目录，详见部署指南
```

桥接模块：`core/ai/weixin_forward.py`、`bridge_commands.py`、`reply_mode.py`、`weixin_worker.py`、`weixin_bind.py`；浏览器集成：`runner.py`；会话状态：`core/session_store.py`。服务模板在 `deploy/`。

## 隐私与运行风险

- 不提交 Cookie、API Key、binding/context、二维码、真实聊天数据库、会话状态或服务器备份。运行目录权限 700、敏感文件 600。
- 队列保存消息文本，目前没有自动清理策略；运营时需要自行制定保留期，避免无限增长。
- 免确认发送存在误发风险，尤其多个会话连续通知时；不确定目标就显式指定编号。
- 扫码上下文可能过期，需先在 ClawBot 发一句话刷新 context_token；失败状态请检查，未知结果不要盲目重发。
- 浏览器自动化及非稳定接口可能失效，可能受到平台限制。仅用于自己有权管理的账号及正常交流，不用于骚扰、刷量或规避平台风控。

## 来源与许可

保留上游版权和 [MIT LICENSE](LICENSE)。微信接入参考 [Tencent/openclaw-weixin](https://github.com/Tencent/openclaw-weixin)。原项目作者、贡献者和原功能说明见上述上游链接与原项目说明。
