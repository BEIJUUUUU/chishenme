# 🍚 吃什么？

<div align="center">
  <img src="docs/banner.png" alt="吃什么？" width="420">
  <br><br>
  <a href="https://github.com/BEIJUUUUU/chishenme/actions/workflows/ci.yml"><img src="https://github.com/BEIJUUUUU/chishenme/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/BEIJUUUUU/chishenme/actions/workflows/docker-publish.yml"><img src="https://github.com/BEIJUUUUU/chishenme/actions/workflows/docker-publish.yml/badge.svg" alt="Docker 镜像"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://github.com/BEIJUUUUU/chishenme/pkgs/container/chishenme"><img src="https://img.shields.io/badge/ghcr.io-chishenme-2496ED.svg" alt="GHCR"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/%E9%85%8D%E7%BD%AE-%E9%9B%B6%EF%BC%8C%E6%89%93%E5%BC%80%E5%8D%B3%E7%94%A8-orange.svg" alt="零配置">
</div>

> 每天自动为全家生成中晚餐菜单 + 买菜清单，到点推送到家人微信。
> 给爸妈用的菜谱机器人 —— 自托管、单容器、**打开即用、零配置、不需要任何密钥**。

**解决的问题**：家里每天为「吃什么」发愁，老人去菜市场不知道买什么，天天买同一种菜。
本项目用「本地家常菜谱库 + 可选的大模型」按「省份菜系 + 时令 + 家人忌口 + 最近吃过的菜」
每天排出一桌搭配合理的家常菜，生成买菜清单，并在固定时间推送到老人手机上的微信里。

## 零配置能用吗？能。

| | 需要配置吗 | 说明 |
|---|---|---|
| 打开网页就能用 | ✅ 不需要 | 默认**免登录**，双击 `启动.bat` 就进首页，不记账号密码 |
| 生成菜单 | ✅ 不需要 | 默认**仅本地菜谱库**模式：122 道跨省家常菜，按时令、荤素、忌口自动搭配，完全离线、不花钱、不联网 |
| 会话密钥 | ✅ 不需要 | 首次运行自动生成随机密钥存到 `data/secret.key`，不用手填 |
| 推到微信 | ⚙️ 需要 | 想要每天自动收到消息，得填一个推送通道的 Webhook（企业微信 1 分钟搞定） |
| AI 自由配菜 | ⚙️ 可选 | 想让大模型按你家口味自由发挥，再选一条通道 —— OpenAI 兼容 / Anthropic 兼容（含 cliproxy 反代）/ 本地 Ollama / Gemini |

---

## 效果长这样

推送到企业微信群的每日消息：

```
🍚 今日菜单 · 今天 午餐 + 晚餐

**午餐**
- 清蒸鲈鱼 · *荤菜* —— 水开后蒸 8 分钟，泼热油
- 西红柿炒鸡蛋 · *素菜* —— 先炒蛋后下番茄
- 醋溜土豆丝 · *素菜* —— 手切更脆，出锅前淋醋
- 紫菜蛋花汤 · *汤*
- 主食：米饭
> 荤素搭配，一荤两素一汤，清淡好消化

**晚餐**
- 香菇油菜 · *素菜*
- 番茄牛腩 · *荤菜* —— 牛腩先焯水，小火炖 40 分钟
- 拍黄瓜 · *凉菜*
- 主食：米饭
> 晚上少油，牛肉补铁

## 🛒 买菜清单
🥬 蔬菜：西红柿×2、土豆、黄瓜、油菜、香菇
🥩 肉蛋类：牛腩、鸡蛋
🐟 水产海鲜：鲈鱼
🧂 调味料：米醋、姜、蒜
```

另外还有两条老人友好的页面：
- **大字版买菜清单** `/plans/<日期>/shopping` —— 一键复制到微信、一键打印。
- **简单做法** `/plans/<日期>/recipes` —— 每道菜的「一句话要点 + 三步做法」，下厨时照着做，也能一键复制/打印。

推送消息里也能带上做法（「设置 → 定时推送 → 推送里带简单做法」开关，默认开）：

```
## 👩‍🍳 午餐简单做法
- 红烧肉：①五花肉切块冷水下锅焯水去沫 ②小火炒冰糖至琥珀色，下肉块裹匀 ③加生抽老抽、姜葱和热水没过，小火炖 40 分钟收汁
- 醋溜土豆丝：①土豆切细丝泡冷水去淀粉 ②热油下干辣椒、蒜片爆香 ③下土豆丝大火炒，加盐和醋快速翻匀
```

---

## 功能

| 能力 | 说明 |
|---|---|
| 🚀 打开即用 | 默认免登录 + 默认仅本地菜谱库，双击启动脚本就能出菜单，不需要任何密钥 |
| 👩‍🍳 每道菜带做法 | 内置 122 道菜**全部**配好「一句话要点 + 三步做法」，出菜单时自动带出；有独立的「简单做法」大字页，可直接复制到微信或打印给老人照着做 |
| 🤖 四条 LLM 通道（可选） | **OpenAI 兼容**（DeepSeek / 通义 / Kimi / 智谱 / 硅基流动 / one-api 网关）· **Anthropic 兼容**（官方 Claude 与 **cliproxy / claude-code-proxy 这类反代**）· **本地 Ollama** · **Google Gemini**；LM Studio / vLLM / llama.cpp 这些本地推理服务走 OpenAI 兼容口即可。接上后 AI 也会按同一格式给出做法 |
| 🧩 一键列出模型 | 设置页有「列出可用模型」按钮，直接向对方要一份模型列表，点一下就填进配置 —— 反代的模型别名常和官方文档不一样，不用再猜 |
| 🧪 假模型服务器 | 自带 `scripts/fake_llm_server.py`，本地起一个假的 OpenAI/Anthropic/Ollama/Gemini 接口，**不花一分钱**就能验证自己的配置链路是否打通 |
| ✅ 三重校验闸门 | 重复菜（N 天窗口）、忌口食材、辣度上限、荤素搭配、健康约束（三高 / 痛风 / 牙口）、时令 |
| 🔁 定点修复重试 | 不合格不是重摇，而是把「具体问题」回传给模型让它改，省 token 更稳 |
| 🛟 本地库兜底 | 重试耗尽、断网或没配密钥时，用内置 122 道家常菜拼出一桌**保证合规**的菜单，永不空手 |
| ⏰ 定时推送 | APScheduler 两个 cron：早上推午餐、下午推晚餐；可提前 1~7 天播报，配置改完热更新 |
| 📮 8 个推送通道 | 企业微信、Server 酱、PushPlus、WxPusher、飞书、钉钉、Bark、自定义 Webhook，可多选 |
| 🛒 自动购物清单 | 按品类（蔬菜 / 肉蛋 / 水产 / 豆制品 / 干货 / 粮油 / 调料）归类去重，重复食材标 ×N |
| ✏️ 全程可编辑 | 加菜、删菜、改食材、改做法、改汤、改主食，改完购物清单与做法快照自动重算 |
| 📚 菜谱库管理 | 122 道内置菜（覆盖 20+ 省菜系）、做法可编辑、启用/停用、手动新增、把 AI 出的好菜连同做法一键收录 |
| 🌶️ 省份差异化 | 按省份映射菜系与地方做法（鲁菜 / 川菜 / 粤菜 / 东北菜 / 西北…），为「给各省人用」而设计 |
| 🔓 访问控制可选 | 默认免登录；要暴露到公网时，在「设置 → 访问控制」一键切成需要账号密码 |
| 📱 移动端友好 | 无构建步骤的响应式页面，手机浏览器打开即用 |

---

## 快速开始

一句话版本：**NAS 上只放一个 `docker-compose.yml`，`docker compose up -d` 自动拉镜像，不需要源码、不需要构建。**

```bash
curl -fsSL https://raw.githubusercontent.com/BEIJUUUUU/chishenme/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

下面按场景分开写：

- **NAS / 服务器** → [方式二](#方式二nason-服务器只放一个-yml自动拉镜像不用源码)（拉镜像，最省事）
- **Windows 本机** → [方式一](#方式一windows-双击启动推荐先试这个)（双击 `启动.bat`）
- **想改代码** → [方式三](#方式三本机手动跑-python)

### 方式一：Windows 双击启动（推荐先试这个）

直接双击项目目录里的 **`启动.bat`**。它会自动：

1. 优先用 Docker 启动（装了 Docker Desktop 的话）；
2. 没装 Docker 就自动建 `.venv` 虚拟环境、装依赖（只做一次）；
3. 启动服务并把浏览器打开到 `http://127.0.0.1:8080`。

停止服务：双击 **`停止.bat`**，或直接关掉标题为「吃什么？ 服务」的那个窗口。
数据存在项目目录下的 `data/` 文件夹里。

> **默认免登录**，打开就是首页，什么都不用填。
> 只有你之后在「设置 → 访问控制」里改成「需要账号密码」时，才用默认账号 **admin / admin123**（改完记得立刻换密码）。

### 方式二：NAS / 服务器（只放一个 yml，自动拉镜像，不用源码）

镜像已发布在 GHCR（支持 **amd64 与 arm64**，群晖 / 威联通 / 树莓派都能跑），
只要下面这个文件 + 一条命令：

```bash
# 在 NAS 上（SSH 进去，随便找个目录）
curl -fsSL https://raw.githubusercontent.com/BEIJUUUUU/chishenme/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

或者手动把这段贴成 `docker-compose.yml`，效果一样：

```yaml
services:
  chishenme:
    image: ghcr.io/beijuuuuu/chishenme:latest
    container_name: chishenme
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      TZ: Asia/Shanghai
      CSM_DATA_DIR: /data
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

打开 `http://<NAS-IP>:8080` 即可。

```bash
docker compose pull && docker compose up -d   # 升级到最新版
docker compose logs -f                        # 看日志
docker compose down                           # 停止
```

> 镜像地址：`ghcr.io/beijuuuuu/chishenme`（也支持 `:sha-xxxxxxx` 与 `:1.2.3` 版本号标签）
>
> 想从源码自己构建（改代码时用）：
> `docker compose -f docker-compose.build.yml up -d --build`
>
> 想让新版镜像自动生效，把 `docker-compose.yml` 末尾注释掉的 Watchtower 段打开即可（每 6 小时检查一次）。

> 会签名的会话密钥不用操心：不配置时程序会自动生成一份随机密钥保存在 `data/secret.key`。
> 默认免登录（家里局域网自用最省事）；如果这台 NAS 会被公网访问，请在
> `docker-compose.yml` 里把 `CSM_AUTH_MODE: password` 的注释去掉，或进「设置 → 访问控制」切换。

### 方式三：本机手动跑 Python

```bash
git clone https://github.com/BEIJUUUUU/chishenme.git
cd chishenme
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### 打开后建议做的三件事（都不强制）

1. **设置 → 家庭画像**：确认省份 + 人数（默认山东 / 4 人）。这一项影响最大，填对就够用了。
2. **设置 → 口味与健康**：家里老人有高血压 / 高血糖 / 痛风 / 牙口不好，勾上；不吃的食材写进忌口。
3. **设置 → 推送通道 + 定时推送**：想要每天自动发到微信，填一个推送通道并打开定时任务。

**可选**：想让 AI 按你家口味自由配菜（而不是固定从菜谱库挑），到「设置 → LLM 模型」选一条通道。
四条通道覆盖了几乎所有接法，详见 [接大模型](#接大模型四条通道) 一节。

配好后再回首页点「生成今天菜单」即可；**没配也照样能用**，只是换成菜谱库搭配。

---

## 接大模型（四条通道）

| 通道 | 什么时候选它 | 需要填什么 |
|---|---|---|
| **OpenAI 兼容** | 云端：DeepSeek / 通义 / Kimi / 智谱 / 硅基流动；网关：one-api / new-api；本地推理：LM Studio / vLLM / llama.cpp / LocalAI | Base URL（填到 `/v1`）、API Key、模型名 |
| **Anthropic 兼容** | 官方 Claude，以及 **cliproxy / claude-code-proxy 这类把 CLI 订阅转成 API 的反代** | Base URL、模型名（反代通常不用 Key） |
| **本地 Ollama** | 想完全离线、零成本 | 地址（容器里填 `http://host.docker.internal:11434`）、模型名 |
| **Google Gemini** | 手边只有 Gemini 的 Key | API Key、模型名 |

### 三个让配置不折腾的设计

1. **地址怎么写都行**。填到域名、填到 `/v1`、甚至把完整 endpoint 直接粘进来，程序都会自动补全，不会拼出 `/v1/chat/completions/chat/completions`。
2. **本地地址可以不填 Key**。Base URL 是 `127.0.0.1` / `localhost` / `192.168.x` / `10.x` / `host.docker.internal` 时按「不校验」处理 —— LM Studio、llama.cpp、cliproxy 反代本来就不需要；而指向公网服务却没填 Key 时，会明确告诉你缺什么，而不是生成一串 401。
3. **「列出可用模型」按钮**。直接向对方要一份模型列表，点一个名字就填进配置。反代的模型别名（`claude-sonnet-4-5` 还是 `anthropic/claude-3.5`）不用再去翻文档猜。

### cliproxy 反代怎么填

假设你的反代跑在局域网某台机器的 `8317` 端口：

```
通道        Anthropic 兼容（Claude / cliproxy 等反代）
Base URL    http://192.168.1.10:8317
API Key     留空（反代一般不校验；如果它校验就填上）
模型名      填反代支持的别名，比如 claude-sonnet-4-5
            不确定就点「列出可用模型」
```

点「测试 LLM 连接」出现绿色 ✅ 就通了。两个细节已经替你处理：

- **官方 API 认 `x-api-key`，有些反代要 `Authorization: Bearer`** —— 后者用「额外请求头」补一行 `Authorization: Bearer xxx` 即可。
- **有些反代无视 `stream=false` 直接吐 SSE 流** —— 遇到这种会被自动识别并把流拼回完整文本，而不是报「返回非 JSON」。

### 本地推理服务怎么填（OpenAI 兼容通道）

| 服务 | Base URL |
|---|---|
| Ollama（用它自己的 OpenAI 兼容口） | `http://host.docker.internal:11434/v1` |
| LM Studio | `http://host.docker.internal:1234/v1` |
| llama.cpp server | `http://host.docker.internal:8080/v1` |
| vLLM | `http://host.docker.internal:8000/v1` |

> 容器里访问宿主机一律用 `host.docker.internal`（compose 已配 `host-gateway`）；
> 服务在另一台机器上就填那台的 IP。忘了 IP 可以先在本机浏览器打开确认。

### 不想烧额度？用自带的假模型

```bash
python scripts/fake_llm_server.py --port 877
```

它会起一个本地假接口，同时模拟 OpenAI / Anthropic / Ollama / Gemini 四种形状，
并且从仓库自带的菜谱库里随机拼菜单（带做法、遵守辣度与忌口约束）。
把「设置 → LLM 模型」的地址指向它，就能验证整条链路是否打通 ——
**用它可以一眼分清「是我配错了」还是「是模型不行」**。

---

## 推送通道怎么拿

### 企业微信机器人（**最推荐给老人**）

免费、无审核、不用公众号，老人只要在微信里进这个群就能收到。

1. 手机企业微信（或个人微信也能用「企业微信」App）新建一个内部群，把家人拉进去。
2. 群 → 右上角 `···` → **群机器人** → 添加机器人 → 复制 Webhook 地址。
3. 粘贴到「设置 → 推送通道 → 企业微信 Webhook」，保存后点「发送测试」。

### Server 酱 / PushPlus / WxPusher

| 通道 | 获取方式 | 说明 |
|---|---|---|
| Server 酱 | <https://sct.ftqq.com> 微信扫码拿 SendKey | 免费额度有限，个人微信直接收 |
| PushPlus | <https://www.pushplus.plus> 微信登录拿 token | 支持建群组一对多推送全家 |
| WxPusher | <https://wxpusher.zjiecode.com> 建应用拿 AppToken，关注后拿 UID | 可按 UID 精准发给某个家人 |
| 飞书 / 钉钉 | 群 → 添加群机器人 → 自定义机器人 Webhook | 年轻人自用顺手 |
| Bark | `https://api.day.app/你的Key` | iOS 原生推送 |
| 自定义 Webhook | 任意可接收 POST 的地址 | 收到 `{title, markdown, plain}`，可接 HomeAssistant / n8n |

---

## 工作原理

```
                 ┌──────────────────────────────────────────┐
   定时触发  ──▶  │ 1. 组装上下文                             │
 (APScheduler)   │    省份菜系 · 时令食材 · 人数 · 健康约束    │
                 │    忌口 · 最近 N 天吃过的菜（防重复）       │
                 └───────────────────┬──────────────────────┘
                                     ▼
                 ┌──────────────────────────────────────────┐
                 │ 2. 出菜单：两条路                          │
                 │    没配大模型 → 本地菜谱库直接搭配（默认）   │
   配了 → 四条通道任选一条                      │
                 └───────────────────┬──────────────────────┘
                                     ▼
                 ┌──────────────────────────────────────────┐
                 │ 3. 本地校验闸门（app/core/pantry.py）      │
                 │    重复 / 忌口 / 辣度 / 荤素 / 健康 / 时令  │
                 └───────┬───────────────────────┬──────────┘
                    有 error                 无 error
                         │                       │
                         ▼                       │
              ┌────────────────────┐             │
              │ 4. 定点修复重试      │  达上限      │
              │ 把问题回传给模型     ├──────┐      │
              └────────────────────┘      │      │
                                          ▼      ▼
                 ┌──────────────────────────────────────────┐
                 │ 5. 兜底：本地菜谱库拼一桌（保证合规）       │
                 └───────────────────┬──────────────────────┘
                                     ▼
                 ┌──────────────────────────────────────────┐
                 │ 6. 汇总购物清单 → 入库 → 多通道推送微信     │
                 └──────────────────────────────────────────┘
```

**为什么要有本地库？** LLM 会幻觉（「西红柿炒月饼」）、会重复、会无视忌口，也不是每个人都愿意配密钥。
所以把「创意」交给 LLM（可选），把「合规判断」和「没网也能用」交给确定性代码 —— 这是本项目最核心的设计取舍。

---

## 目录结构

```
app/
├── main.py               FastAPI 装配、启动引导、异常处理
├── config.py             环境变量配置（CSM_* 前缀）
├── models.py             SQLite 表：settings / users / dishes / plans / push_logs / generation_logs
├── runtime_config.py     家庭配置模型 AppConfig + WebUI 表单 Schema（页面数据驱动）
├── scheduler.py          APScheduler 定时任务（可热更新）
├── services.py           推送编排 + 落库
├── security.py           PBKDF2 密码 + 签名 Cookie 会话
├── core/
│   ├── generator.py      生成 → 校验 → 重试 → 兜底 → 入库
│   ├── pantry.py         本地菜谱库、健康规则、校验、兜底拼菜
│   ├── prompt.py         提示词（家庭画像 + 时令 + 防重复）
│   ├── shopping.py       购物清单归类聚合
│   ├── season.py         时令计算
│   └── message.py        推送文本渲染（markdown / 纯文本）
├── llm/                  四条通道：OpenAI 兼容 / Anthropic 兼容 / Ollama / Gemini
│                         + 自定义请求头、模型列表、JSON 健壮解析
│   ├── openai_compat.py      DeepSeek、各类网关、LM Studio、vLLM、llama.cpp
│   ├── anthropic_compat.py   官方 Claude 与 cliproxy 等反代（含 SSE 兜底解析）
│   ├── ollama_provider.py    本地 Ollama
│   ├── gemini_provider.py    Google Gemini（可强制 JSON 输出）
│   └── factory.py            通道注册、可用性判断、连通性自检、模型列表
├── notify/               8 个推送通道 + 注册表
├── routers/              auth / pages / settings / dishes / api
├── data/                 内置菜谱库、做法库、时令表
├── templates/            Jinja2 模板（10 个页面）
└── static/               原生 CSS + JS，零 CDN 依赖，离线可用
scripts/
├── start_server.ps1      记录 PID 后拉起服务（启动.bat 调用）
├── stop_server.ps1       按 PID / 端口 / 命令行三级精确停止
├── fake_llm_server.py    本地假模型服务器（模拟四种接口，验证配置用）
└── offline_demo.py       不配 LLM 也能跑通全流程，打印今天的菜单
tests/                    pytest：校验、购物清单、生成全链路、Web 冒烟、
                          四条 LLM 通道的报文形状与真实 HTTP 往返
启动.bat / 停止.bat         Windows 双击即可启动 / 停止
docker-compose.yml        拉 GHCR 现成镜像（NAS 用这个）
docker-compose.build.yml  从源码本地构建（改代码时用）
.github/workflows/        ci.yml（测试 + 构建校验）· docker-publish.yml（发布多架构镜像到 GHCR）
```

---

## HTTP API

免登录模式下（默认）直接就能调；切到需要登录后要先登录拿 Cookie。可在「API 文档」`/api/docs` 里直接试。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查（Docker healthcheck 用） |
| GET | `/api/plans/{date}` | 取某天菜单 + 购物清单 |
| GET | `/api/plans/{date}/markdown` | 取可直接发送的 markdown / 纯文本 |
| POST | `/api/generate` | 生成菜单 `{target_date, meals, force}` |
| POST | `/api/push` | 推送 `{target_date, channels}` |
| POST | `/api/test/llm` | 测试 LLM 连通性 |
| POST | `/api/llm/models` | 列出当前通道的可用模型 |
| POST | `/api/test/push/{channel}` | 测试某推送通道 |
| GET | `/api/stats` | 生成统计 |

---

## 各省份适配与做法库

菜谱分成两个文件，职责分开、各自升级：

| 文件 | 内容 | 什么时候改 |
|---|---|---|
| `app/data/dishes.json` | 菜名、省份、类型、季节、主要食材、标签、辣度 | 新增一道菜时 |
| `app/data/howto.json` | 每道菜的「一句话做法要点 + 三步做法」 | 想改做法、给自家菜补做法时 |

`howto.json` 里每道菜长这样：

```json
"醋溜土豆丝": {
  "howto": "切丝泡水去淀粉，出锅前淋醋",
  "steps": "①土豆切细丝泡冷水去淀粉 ②热油下干辣椒、蒜片爆香 ③下土豆丝大火炒，加盐和醋快速翻匀"
}
```

**两种改法**：

1. 直接在 WebUI「菜谱库」里改 —— 鼠标点一下就能改做法要点和步骤，立刻生效。
2. 改 `howto.json` 后重启（或点「设置 → 同步内置菜谱库」）—— 已有菜如果做法为空会被自动补上，**不会覆盖你自己写过的做法**。

设置里选「四川」时，LLM 会按川菜口味出菜，本地兜底库也优先挑川菜与通用菜（含上海→苏浙、重庆→川、东三省→东北等别名映射）。
欢迎 PR 扩充各省菜谱与做法 —— 这是让项目真正「给各省人用」的关键。

---

## 常见问题

**Q：一定要配密钥 / 一定要有大模型吗？**
都不用。默认就是「仅本地菜谱库」模式：122 道家常菜按时令、荤素、忌口自动搭配，离线可用、零成本。
大模型是可选的加分项，接法见 [接大模型](#接大模型四条通道)。

**Q：我有 cliproxy / 各种反代，能接吗？**
能。反代分两类：Anthropic 形状的（cliproxy、claude-code-proxy）选**「Anthropic 兼容」**通道；
OpenAI 形状的（one-api、new-api、各类中转站）选**「OpenAI 兼容」**通道。
两者都支持「本地/局域网地址不填 Key」，模型别名不用猜 —— 点「列出可用模型」直接拉一份回来点选。

**Q：菜品有做法吗？我想照着做。**
有。内置 122 道菜**每道都配好了**「一句话要点 + 三步做法」，本地模式也能带出来：
- 首页 / 菜单详情：每道菜后面跟一句要点；
- 「简单做法」页（`/plans/<日期>/recipes`，首页有入口）：列出三步做法，大字排版，可一键复制或打印；
- 推送消息里也会附「👩‍🍳 简单做法」（可在「设置 → 定时推送」关掉）。

想改做法或给自家菜补做法：直接在「菜谱库」页面改，或编辑 `app/data/howto.json` 后重启。

**Q：为什么不用登录？被别人看到怎么办？**
默认免登录是为了「打开即用」——家里局域网自用，省掉记账号密码的麻烦。
代价是：**能访问到这个网址的人就是管理员**。所以只要不是把端口映射到公网，就没事；
一旦要暴露到公网（端口转发、内网穿透），请务必去「设置 → 访问控制」改成「需要账号密码」，
或者在 `docker-compose.yml` 里设 `CSM_AUTH_MODE: password` 把登录锁死。

**Q：老人只用微信，没有企业微信怎么办？**
注册一个企业微信（个人可免费注册，无需企业资质），建群、加群机器人，然后让家人在微信里接收「企业微信」消息即可。这是目前对老人最省事的方案。

**Q：容器访问不到 NAS 上的 Ollama？**
`docker-compose.yml` 已配 `host.docker.internal:host-gateway`，地址填 `http://host.docker.internal:11434`。
若 Ollama 在另一台机器，直接填那台的 IP:11434，并确认 Ollama 监听 `0.0.0.0`（`OLLAMA_HOST=0.0.0.0`）。

**Q：为什么生成的菜被「打回」了？**
看「日志 → AI 生成记录」里的说明列，会写明原因（重复 / 忌口 / 辣度 / 荤素失衡）。调整设置或点「换一桌」即可。

**Q：数据存在哪？怎么备份？**
`./data/chishenme.db`（SQLite + WAL）、`./data/secret.key` 与 `./data/logs/`。备份直接拷 `data` 目录。

**Q：推送时间不准？**
确认容器时区。`docker-compose.yml` 已设 `TZ=Asia/Shanghai`。

**Q：能不能给爸妈各自发不同内容？**
WxPusher 支持按 UID 精准推送，可自行扩展成多接收人；当前版本已预留 `PushLog.target` 字段。

---

## 路线图

- [ ] 每周菜单一次生成（7 天批量，去重跨天生效）
- [ ] 菜价估算与预算控制（接入本地菜价数据）
- [ ] 语音播报（TTS 推语音条，方便不识字老人）
- [ ] 拍照识别冰箱剩余食材 → 优先消耗
- [ ] 多家庭 / 多租户注册
- [ ] 各省份菜谱库众包扩充

---

## 开发

```bash
pip install -r requirements-dev.txt
pytest -q                       # 全部测试
ruff check app tests scripts    # 代码检查
python scripts/offline_demo.py  # 不配 LLM 也能跑通全流程，打印今天的菜单
```

Windows 上调试启动脚本时可以直接指定解释器，跳过环境准备：

```bat
set CSM_PYTHON=D:\python312\python.exe
set CSM_PORT=8081
启动.bat
```

可用环境变量：`CSM_PORT`（端口）、`CSM_PYTHON`（指定解释器）、`CSM_FORCE_DOCKER=1`（强制容器）、`CSM_NO_BROWSER=1`（不自动开浏览器）。

## 许可证

MIT
