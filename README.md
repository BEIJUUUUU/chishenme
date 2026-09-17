# 🍚 吃什么？

> 每天自动为全家生成中晚餐菜单 + 买菜清单，到点推送到家人微信。
> 给爸妈用的菜谱机器人 —— 自托管、单容器、一条 `docker compose up -d` 搞定。

**解决的问题**：家里每天为「吃什么」发愁，老人去菜市场不知道买什么，天天买同一种菜。
本项目用 LLM 按「省份菜系 + 时令 + 家人忌口 + 最近吃过的菜」每天排出一桌搭配合理的家常菜，
生成买菜清单，并在固定时间推送到老人手机上的微信里。

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

另外还有一条老人友好的**大字版买菜清单**页面（`/plans/<日期>/shopping`），一键复制到微信、一键打印。

---

## 功能

| 能力 | 说明 |
|---|---|
| 🤖 双 LLM 通道 | OpenAI 兼容 API（DeepSeek / 通义 / Kimi / 智谱 / 硅基流动…）与**本地 Ollama**，WebUI 里一键切换 |
| ✅ 三重校验闸门 | 重复菜（N 天窗口）、忌口食材、辣度上限、荤素搭配、健康约束（三高 / 痛风 / 牙口）、时令 |
| 🔁 定点修复重试 | 不合格不是重摇，而是把「具体问题」回传给模型让它改，省 token 更稳 |
| 🛟 本地库兜底 | 重试耗尽或断网时，用内置 130+ 道家常菜拼出一桌**保证合规**的菜单，永不空手 |
| ⏰ 定时推送 | APScheduler 两个 cron：早上推午餐、下午推晚餐；可提前 1~7 天播报，配置改完热更新 |
| 📮 8 个推送通道 | 企业微信、Server 酱、PushPlus、WxPusher、飞书、钉钉、Bark、自定义 Webhook，可多选 |
| 🛒 自动购物清单 | 按品类（蔬菜 / 肉蛋 / 水产 / 豆制品 / 干货 / 粮油 / 调料）归类去重，重复食材标 ×N |
| ✏️ 全程可编辑 | 加菜、删菜、改食材、改汤、改主食，改完购物清单自动重算 |
| 📚 菜谱库管理 | 130+ 道内置菜（覆盖 20+ 省菜系）、启用/停用、手动新增、把 AI 出的好菜一键收录 |
| 🌶️ 省份差异化 | 按省份映射菜系与地方做法（鲁菜 / 川菜 / 粤菜 / 东北菜 / 西北…），为「给各省人用」而设计 |
| 📱 移动端友好 | 无构建步骤的响应式页面，手机浏览器打开即用 |

---

## 快速开始（NAS / 服务器）

```bash
git clone https://github.com/<你的用户名>/chishenme.git
cd chishenme
# 改掉密钥（重要）
sed -i 's/change-me-to-a-random-string/你的随机字符串/' docker-compose.yml
docker compose up -d
```

打开 `http://<NAS-IP>:8080`，默认账号 **admin / admin123**（登录后立刻在设置里改密码）。

> 仓库名建议用 `chishenme`（GitHub 不支持全角问号），项目页面标题保留「吃什么？」。

### 首次配置四步

1. **设置 → 家庭画像**：省份、人数、菜品数、辣度上限、主食、预算。
2. **设置 → 口味与健康**：勾选老人的健康约束（高血压 / 高血糖 / 痛风 / 牙口不好…），填忌口食材。
3. **设置 → LLM 模型**：
   - 云端：填 Base URL + API Key + 模型名，点右上角「测试 LLM 连接」。
   - 本地：Ollama 地址填 `http://host.docker.internal:11434`（compose 已配 `host-gateway`），模型填 `qwen2.5:7b`。
4. **设置 → 推送通道**：勾选通道、填密钥，回「设置 → 账号安全」逐个点「发送测试」。
5. 回首页点「生成今天菜单」，满意后打开「定时推送」，从此每天自动到微信。

### 本地开发（不上容器）

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

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
                 │ 2. LLM 生成 JSON 菜单                     │
                 │    OpenAI 兼容 API  或  本地 Ollama        │
                 │    response_format=json_object            │
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

**为什么要有本地库？** LLM 会幻觉（「西红柿炒月饼」）、会重复、会无视忌口。
把「创意」交给 LLM，把「合规判断」交给确定性代码，再用本地库兜住最坏情况 —— 这是本项目最核心的设计取舍。

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
├── llm/                  BaseLLM + OpenAI 兼容 + Ollama + JSON 健壮解析
├── notify/               8 个推送通道 + 注册表
├── routers/              auth / pages / settings / dishes / api
├── data/                 内置菜谱库、时令表
├── templates/            Jinja2 模板（9 个页面）
└── static/               原生 CSS + JS，零 CDN 依赖，离线可用
tests/                    pytest：校验、购物清单、生成全链路、Web 冒烟
```

---

## HTTP API

除 `/healthz` 外都需要登录态（Cookie），可在「API 文档」`/api/docs` 里直接试。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查（Docker healthcheck 用） |
| GET | `/api/plans/{date}` | 取某天菜单 + 购物清单 |
| GET | `/api/plans/{date}/markdown` | 取可直接发送的 markdown / 纯文本 |
| POST | `/api/generate` | 生成菜单 `{target_date, meals, force}` |
| POST | `/api/push` | 推送 `{target_date, channels}` |
| POST | `/api/test/llm` | 测试 LLM 连通性 |
| POST | `/api/test/push/{channel}` | 测试某推送通道 |
| GET | `/api/stats` | 生成统计 |

---

## 各省份适配

`app/data/dishes.json` 每道菜带 `province` / `category` / `season` / `ingredients` / `tags` / `spicy`。
设置里选「四川」时，LLM 会按川菜口味出菜，本地兜底库也优先挑川菜与通用菜（含上海→苏浙、重庆→川、东三省→东北等别名映射）。

想为你的省份补充菜谱：WebUI「菜谱库 → 新增一道菜」，或直接往 `dishes.json` 里加条目后重启。
欢迎 PR 扩充各省菜谱库 —— 这是让项目真正「给各省人用」的关键。

---

## 常见问题

**Q：一定要有 API Key 吗？**
不是。用本地 Ollama 可完全离线零成本；即使两者都没有，本地菜谱库兜底也能每天排出一桌合规的菜。

**Q：老人只用微信，没有企业微信怎么办？**
注册一个企业微信（个人可免费注册，无需企业资质），建群、加群机器人，然后让家人在微信里接收「企业微信」消息即可。这是目前对老人最省事的方案。

**Q：容器访问不到 NAS 上的 Ollama？**
`docker-compose.yml` 已配 `host.docker.internal:host-gateway`，地址填 `http://host.docker.internal:11434`。
若 Ollama 在另一台机器，直接填那台的 IP:11434，并确认 Ollama 监听 `0.0.0.0`（`OLLAMA_HOST=0.0.0.0`）。

**Q：为什么生成的菜被「打回」了？**
看「日志 → AI 生成记录」里的说明列，会写明原因（重复 / 忌口 / 辣度 / 荤素失衡）。调整设置或点「换一桌」即可。

**Q：数据存在哪？怎么备份？**
`./data/chishenme.db`（SQLite + WAL）与 `./data/logs/`。备份直接拷 `data` 目录。

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
pip install -r requirements.txt pytest pytest-asyncio
pytest -q                     # 全部测试
python scripts/offline_demo.py  # 不配 LLM 也能跑通全流程，打印今天的菜单
```

## 许可证

MIT
