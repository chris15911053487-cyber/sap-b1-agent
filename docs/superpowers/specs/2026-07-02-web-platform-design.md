# SAP B1 数据库 AI 智能体 — Web 平台设计规格

> 日期：2026-07-02  
> 状态：已确认  
> 关联项目：sap-b1-db-agent

## 1. 背景与目标

### 1.1 当前状态

`sap-b1-db-agent` 是一个基于 DeepSeek API 的 CLI 工具，用中文自然语言查询 SAP Business One 的 SQL Server 数据库。核心功能已实现：

- 意图识别（QUERY / BUILD_SP / VERIFY / CHAT）
- Text-to-SQL 生成（含硬编码 SAP B1 表结构知识）
- SQL 安全执行（pymssql/FreeTDS）
- 结果中文解读
- 存储过程架构设计
- 数据校验（库存一致性等）

### 1.2 目标

将 CLI 工具升级为 **多合一 Web 平台**，给 SAP B1 实施顾问团队使用：

- **Web 浏览器** 作为主交互入口
- **IM 机器人**（飞书/企微/钉钉）预留 API 接口
- **Docker 一键部署** 到客户内网环境

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────┐
│                    Nginx (反向代理)               │
├──────────────────────┬──────────────────────────┤
│   Vue 3 SPA (静态)    │   FastAPI (API 服务)      │
│   端口 80/443        │   端口 8000               │
│                      │                           │
│   聊天界面            │   /api/chat     聊天接口   │
│   查询模式            │   /api/query    单次查询   │
│   SP 构建器           │   /api/sp       存储过程   │
│   数据校验            │   /api/verify   数据校验   │
│   历史记录            │   /api/history  对话历史   │
│   系统配置            │   /api/webhook  IM 回调   │
│                      │   /ws          流式输出    │
└──────────────────────┴──────────────────────────┘
         │                        │
         ▼                        ▼
    浏览器访问              IM 机器人 (飞书/企微/钉钉)
```

### 2.1 核心原则

- 现有 `agent/`、`database/`、`config/` 模块保持不变，FastAPI 通过 import 复用
- WebSocket/SSE 实现流式输出（DeepSeek 支持 stream 模式）
- 前端纯静态，Nginx 反代 API，同源部署，无需 CORS
- 一个 `docker-compose up` 启动全部

---

## 3. API 设计

### 3.1 核心端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 对话入口，自动识别意图并返回完整结果 |
| `POST` | `/api/chat/stream` | 流式对话（SSE），逐事件推送 |
| `GET` | `/api/history` | 对话历史列表 |
| `GET` | `/api/history/{id}` | 某次对话详情（含消息列表） |
| `DELETE` | `/api/history/{id}` | 删除对话 |
| `POST` | `/api/connection/test` | 测试数据库连接 |
| `GET` | `/api/schema/tables` | 获取已知表结构列表 |
| `POST` | `/api/webhook/feishu` | 飞书机器人回调 |
| `POST` | `/api/webhook/wecom` | 企微机器人回调 |
| `POST` | `/api/webhook/dingtalk` | 钉钉机器人回调 |

### 3.2 请求/响应格式

```
POST /api/chat
Content-Type: application/json

{
  "message": "查一下最近30天的销售订单",
  "database": "test",
  "conversation_id": null
}

Response 200:
{
  "conversation_id": "abc123",
  "intent": "QUERY",
  "sql": "SELECT TOP 100 T0.DocEntry, T0.DocDate, T0.CardName ...",
  "data": {
    "columns": ["DocEntry", "DocDate", "CardName", "DocTotal"],
    "rows": [[1, "2026-06-15", "客户A", 15000.00], ...]
  },
  "explanation": "最近30天共有 23 笔销售订单，总金额 ¥156,000.00。其中..."
}
```

### 3.3 流式输出（SSE）

```
POST /api/chat/stream
Content-Type: application/json

{"message": "查库存", "database": "test"}

Response (text/event-stream):
event: intent       data: {"intent": "QUERY"}
event: sql          data: {"sql": "SELECT TOP 100 ..."}
event: data         data: {"columns": [...], "rows": [[...]]}
event: explanation  data: {"text": "当前库存..."}
event: done         data: {}
```

### 3.4 错误响应

```json
{
  "error": {
    "code": "DB_CONNECTION_FAILED",
    "message": "无法连接到数据库 test"
  }
}
```

---

## 4. 前端设计

### 4.1 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 框架 | Vue 3 (Composition API) | 生态成熟，中文社区活跃 |
| UI 组件库 | Naive UI | 中文友好，组件丰富，TypeScript 原生 |
| 构建工具 | Vite | 快速开发构建 |
| 状态管理 | Pinia | Vue 3 官方推荐 |
| HTTP 客户端 | axios | 拦截器、SSE 支持 |
| 代码高亮 | highlight.js | SQL 语法高亮 |
| 表格导出 | xlsx (SheetJS) | CSV/Excel 导出 |
| Markdown | marked | AI 回复渲染 |

### 4.2 页面结构

```
┌──────────────────────────────────────────────┐
│  🏠 首页    💬 对话    📊 校验    ⚙️ 设置    │  ← 顶部导航
├────────────┬─────────────────────────────────┤
│            │                                 │
│  对话列表   │    聊天区域                      │
│            │                                 │
│  · 销售查询 │  ┌─────────────────────────┐   │
│  · 库存检查 │  │ 用户消息                  │   │
│  · 新对话   │  │ AI 回复：                 │   │
│            │  │  [意图标签] [SQL代码块]    │   │
│  + 新建    │  │  [数据表格] [中文解读]     │   │
│            │  └─────────────────────────┘   │
│            │  ┌─────────────────────────┐   │
│            │  │ 输入框              [发送]│   │
│            │  └─────────────────────────┘   │
└────────────┴─────────────────────────────────┘
```

### 4.3 三个核心页面

**对话页（主界面）**

- 左侧：对话历史列表，按数据库分组，支持重命名和删除
- 中间：聊天区域
  - 每条 AI 消息依次展示：意图标签 → SQL 代码块（可复制）→ 数据表格（可排序、可导出 CSV）→ 中文解读
  - 支持流式输出：逐事件渲染
- 底部：输入框，Shift+Enter 换行，Enter 发送
- 顶部下拉：选择目标数据库（test / production）

**数据校验页**

- 显示预设校验项列表（库存一致性、负库存检测、总账核对）
- 点击执行单项或一键全部执行
- 校验结果用状态卡片展示（✅ 通过 / ❌ 异常 / ⚠️ 警告）
- 异常项展开显示详细数据

**设置页**

- 数据库配置选择（从 config.yaml 加载）
- 表结构列表浏览
- "测试连接"按钮（调用 `/api/connection/test`）
- 当前 API 状态指示

### 4.4 组件树

```
App.vue
├── LayoutHeader.vue          # 顶部导航
├── router-view
│   ├── ChatView.vue
│   │   ├── ConversationList.vue   # 左侧对话列表
│   │   ├── ChatMessage.vue        # 单条消息（用户/AI）
│   │   │   ├── IntentBadge.vue    # 意图标签
│   │   │   ├── SqlBlock.vue       # SQL 代码块（高亮+复制）
│   │   │   ├── DataTable.vue      # 结果表格（排序+导出）
│   │   │   └── Explanation.vue    # Markdown 解读
│   │   └── ChatInput.vue          # 输入框
│   ├── VerifyView.vue
│   │   └── VerifyCard.vue         # 校验结果卡片
│   └── SettingsView.vue
│       └── TableSchemaList.vue    # 表结构列表
```

---

## 5. 项目结构

```
sap-b1-db-agent/
├── backend/                    # 新增：FastAPI 应用
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口 + 生命周期管理
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── chat.py             # /api/chat, /api/chat/stream
│   │   ├── history.py          # /api/history/*
│   │   ├── connection.py       # /api/connection/test
│   │   ├── schema.py           # /api/schema/*
│   │   └── webhook.py          # /api/webhook/*
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_service.py     # 编排 agent 调用
│   │   └── history_service.py  # 对话持久化（SQLite）
│   └── middleware/
│       ├── __init__.py
│       └── error_handler.py    # 统一异常处理
├── frontend/                   # 新增：Vue 3 SPA
│   ├── src/
│   │   ├── views/
│   │   │   ├── ChatView.vue
│   │   │   ├── VerifyView.vue
│   │   │   └── SettingsView.vue
│   │   ├── components/
│   │   │   ├── ChatMessage.vue
│   │   │   ├── SqlBlock.vue
│   │   │   ├── DataTable.vue
│   │   │   ├── ConversationList.vue
│   │   │   ├── IntentBadge.vue
│   │   │   ├── ChatInput.vue
│   │   │   ├── VerifyCard.vue
│   │   │   └── TableSchemaList.vue
│   │   ├── stores/
│   │   │   ├── chat.ts
│   │   │   └── settings.ts
│   │   ├── api/
│   │   │   └── client.ts       # axios 封装 + SSE 处理
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── App.vue
│   │   └── main.ts
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── agent/                      # 现有，基本不动
│   ├── core.py                 # 仅新增 process_stream() 方法
│   └── ...
├── config/                     # 现有，不动
├── database/                   # 现有，不动
├── tests/                      # 现有 + 新增 backend API 测试
├── docker-compose.yml          # 更新：加 Nginx 服务
├── Dockerfile                  # 更新：多阶段构建
├── nginx.conf                  # 新增：Nginx 配置
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-07-02-web-platform-design.md
```

### 5.1 现有代码改动范围

- `agent/core.py`：新增 `process_stream()` 生成器方法，支持流式 yield
- 其他 `agent/`、`database/`、`config/` 模块：**不动内部逻辑**
- `requirements.txt`：新增 `fastapi`、`uvicorn`、`sse-starlette`、`aiosqlite`

---

## 6. 部署设计

### 6.1 Docker 多阶段构建

```
阶段1: node:20-alpine
  npm ci → npm run build → 产出 dist/

阶段2: python:3.11-slim-bookworm
  安装 FreeTDS + Python 依赖 → 复制后端代码

阶段3: nginx:alpine
  复制前端 dist/ → /usr/share/nginx/html/
  复制 nginx.conf → /etc/nginx/conf.d/default.conf
```

### 6.2 docker-compose.yml

```yaml
services:
  app:
    build:
      context: .
      target: backend
    env_file: .env
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      - ./logs:/app/logs
    expose:
      - "8000"
    restart: unless-stopped

  nginx:
    build:
      context: .
      target: frontend
    ports:
      - "80:80"
    depends_on:
      - app
    restart: unless-stopped
```

### 6.3 Nginx 路由

```
/            → 前端静态文件
/api/*       → proxy_pass http://app:8000
/ws          → proxy_pass http://app:8000 (WebSocket upgrade)
```

### 6.4 环境变量

```
DEEPSEEK_API_KEY=sk-xxx          # 必需
DEEPSEEK_BASE_URL=https://api.deepseek.com
AGENT_ENV=production
DB_TEST_HOST=192.168.1.100       # 示例
DB_TEST_PORT=1433
DB_TEST_DATABASE=SBO_DEMO
DB_TEST_USERNAME=sa
DB_TEST_PASSWORD=xxx
```

---

## 7. 实现分期

| 阶段 | 内容 | 预估工期 |
|------|------|---------|
| **一期** | FastAPI 后端骨架 + `/api/chat`（非流式）+ 历史记录 SQLite | 后端先跑通 |
| **二期** | Vue 3 前端骨架 + Naive UI + 对话页面（非流式） | Web 可用 |
| **三期** | 流式输出 SSE + 数据校验页面 + 设置页面 | 完整体验 |
| **四期** | IM webhook 端点 + Docker 多阶段构建 + Nginx 集成 | 可交付 |
| **五期** | 多轮对话上下文、数据库切换、错误日志优化 | 增强 |

---

## 8. 非功能需求

### 8.1 安全

- 数据库密码通过 `.env` 注入，不提交到 Git
- SQL 执行保留现有安全限制（禁止 DROP/TRUNCATE/无条件 DELETE）
- API 不做认证（内网部署，依赖网络隔离）
- 前端不展示完整数据库连接信息

### 8.2 性能

- 首次查询响应时间 < 5 秒（含 API 调用）
- 流式输出首字节延迟 < 2 秒
- 前端静态资源 gzip 压缩，总体 < 500KB

### 8.3 可维护性

- 后端与现有 agent 模块解耦，互不修改内部逻辑
- 前端组件独立，每个组件职责单一
- 所有 API 文档通过 FastAPI 自动生成（/docs 端点）

---

## 9. 风险与假设

| 风险 | 缓解措施 |
|------|---------|
| DeepSeek API 内网不可达 | 后续支持 Ollama 等本地模型，配置项预留 |
| pymssql/FreeTDS 兼容性 | 已有 TDS 版本配置，多环境已验证 |
| 前端学习成本 | Naive UI 文档齐全，组件即拿即用 |
| 流式输出实现复杂 | SSE 比 WebSocket 简单，FastAPI 原生支持 |
