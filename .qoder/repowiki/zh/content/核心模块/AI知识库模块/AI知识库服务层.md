# AI知识库服务层

<cite>
**本文引用的文件**
- [app/services/ai_service.py](file://app/services/ai_service.py)
- [app/models/ai_kb.py](file://app/models/ai_kb.py)
- [app/utils/markdown.py](file://app/utils/markdown.py)
- [app/utils/outline.py](file://app/utils/outline.py)
- [app/blueprints/ai.py](file://app/blueprints/ai.py)
- [app/config.py](file://app/config.py)
- [app/extensions.py](file://app/extensions.py)
- [app/__init__.py](file://app/__init__.py)
- [requirements.txt](file://requirements.txt)
</cite>

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖分析](#依赖分析)
7. [性能考虑](#性能考虑)
8. [故障排除指南](#故障排除指南)
9. [结论](#结论)
10. [附录](#附录)

## 简介
本文件面向AI知识库服务层，系统化梳理从源文档到Wiki条目的完整处理链路，覆盖状态机管理、源文档处理管道、错误恢复机制、链接解析与跨文档引用、向量嵌入与RAG检索（可选）、增量更新策略、缓存与性能优化、OpenAI兼容SDK封装、并发与后台任务调度，以及蓝图层交互与中间件集成。文档以“可读性优先”的原则，结合图示与路径引用，帮助开发者快速理解与扩展。

## 项目结构
- 服务层位于 app/services，核心为 ai_service.py，负责LLM封装、Wiki构建、链接解析、异步构建与RAG问答。
- 数据模型位于 app/models，核心为 ai_kb.py，定义AI知识库、源文档、文章、链接、分片等实体及状态枚举。
- 工具函数位于 app/utils，包括Markdown渲染与wikilink收集、Editor.js内容提取。
- 蓝图层位于 app/blueprints，ai.py 提供知识库管理、构建、浏览、图谱、聊天等路由。
- 配置与扩展位于 app/config.py 与 app/extensions.py，统一注入数据库、登录、CSRF、AI相关参数。
- 应用工厂位于 app/__init__.py，注册蓝图、扩展与上下文处理器。

```mermaid
graph TB
subgraph "应用层"
BP_AI["蓝图: ai.py"]
CFG["配置: config.py"]
EXT["扩展: extensions.py"]
end
subgraph "服务层"
SVC_AI["服务: ai_service.py"]
end
subgraph "模型层"
M_AIKB["模型: ai_kb.py"]
end
subgraph "工具层"
U_MD["工具: utils/markdown.py"]
U_OUT["工具: utils/outline.py"]
end
BP_AI --> SVC_AI
SVC_AI --> M_AIKB
SVC_AI --> U_MD
SVC_AI --> U_OUT
BP_AI --> CFG
BP_AI --> EXT
```

图表来源
- [app/blueprints/ai.py:1-279](file://app/blueprints/ai.py#L1-L279)
- [app/services/ai_service.py:1-408](file://app/services/ai_service.py#L1-L408)
- [app/models/ai_kb.py:1-121](file://app/models/ai_kb.py#L1-L121)
- [app/utils/markdown.py:1-87](file://app/utils/markdown.py#L1-L87)
- [app/utils/outline.py:1-136](file://app/utils/outline.py#L1-L136)
- [app/config.py:1-83](file://app/config.py#L1-L83)
- [app/extensions.py:1-17](file://app/extensions.py#L1-L17)

章节来源
- [app/__init__.py:11-101](file://app/__init__.py#L11-L101)
- [app/blueprints/ai.py:1-279](file://app/blueprints/ai.py#L1-L279)
- [app/services/ai_service.py:1-408](file://app/services/ai_service.py#L1-L408)
- [app/models/ai_kb.py:1-121](file://app/models/ai_kb.py#L1-L121)
- [app/utils/markdown.py:1-87](file://app/utils/markdown.py#L1-L87)
- [app/utils/outline.py:1-136](file://app/utils/outline.py#L1-L136)
- [app/config.py:1-83](file://app/config.py#L1-L83)
- [app/extensions.py:1-17](file://app/extensions.py#L1-L17)

## 核心组件
- LLM客户端封装：统一OpenAI兼容SDK调用，支持多厂商与本地代理，动态加载client，避免重复初始化。
- Wiki构建器：将源文档转换为标准模板的Markdown条目，输出标题、别名、摘要、标签、正文与相关条目列表。
- 链接解析器：扫描条目中的[[Title]]占位符，基于标题/别名/slug建立索引，生成双向链接表与红链统计。
- 异步构建流水线：后台线程执行构建，维护源文档状态机与知识库整体状态机，失败回滚与错误消息持久化。
- 可选RAG问答：基于关键词重排Top-N条目，拼接上下文后调用LLM回答；向量存储与嵌入模型预留（需启用RAG）。
- 蓝图交互：提供知识库创建、编辑、构建、浏览、图谱、聊天等端点，配合权限控制与状态查询。

章节来源
- [app/services/ai_service.py:47-86](file://app/services/ai_service.py#L47-L86)
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- [app/services/ai_service.py:313-381](file://app/services/ai_service.py#L313-L381)
- [app/services/ai_service.py:391-408](file://app/services/ai_service.py#L391-L408)
- [app/blueprints/ai.py:143-173](file://app/blueprints/ai.py#L143-L173)

## 架构总览
服务层围绕“知识库-源文档-文章-链接”四元组展开，通过LLM生成文章，再进行wikilink解析，最终形成可浏览的Wiki与可选的RAG问答能力。蓝图层负责权限校验、状态查询与UI交互，配置层提供模型与目录参数。

```mermaid
sequenceDiagram
participant Client as "客户端"
participant BP as "蓝图 : ai.py"
participant Svc as "服务 : ai_service.py"
participant DB as "数据库 : ai_kb.py"
participant LLM as "LLM客户端"
participant FS as "文件系统"
Client->>BP : "POST /ai/<id>/build"
BP->>Svc : "build_wiki_async(app, ai_kb_id, only_pending)"
Svc->>DB : "设置状态 BUILDING"
loop 遍历待处理源文档
Svc->>LLM : "chat(系统提示+用户提示)"
LLM-->>Svc : "JSON结构化输出"
Svc->>DB : "upsert_article(...)"
Svc->>FS : "_write_article_file(...)"
end
Svc->>Svc : "resolve_links(ai_kb)"
Svc->>DB : "设置状态 READY / 记录错误信息"
BP-->>Client : "任务已启动"
```

图表来源
- [app/blueprints/ai.py:143-156](file://app/blueprints/ai.py#L143-L156)
- [app/services/ai_service.py:313-341](file://app/services/ai_service.py#L313-L341)
- [app/services/ai_service.py:296-311](file://app/services/ai_service.py#L296-L311)
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:204-230](file://app/services/ai_service.py#L204-L230)
- [app/services/ai_service.py:196-202](file://app/services/ai_service.py#L196-L202)
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)

## 详细组件分析

### LLM客户端封装（OpenAI兼容）
- 功能要点
  - 基于当前应用配置动态构造client，支持base_url与api_key，模型名可按知识库覆盖。
  - 提供chat方法，固定系统与用户消息结构，支持响应格式约束。
  - 导入异常保护，缺失SDK时抛出明确运行时错误。
- 并发与稳定性
  - client惰性初始化，避免重复导入与初始化开销。
  - 失败时保留错误消息，便于上层状态机记录与展示。

```mermaid
classDiagram
class LLMClient {
+base_url : str
+api_key : str
+model : str
-_client
+client
+chat(system, user, temperature, response_format) str
}
```

图表来源
- [app/services/ai_service.py:47-86](file://app/services/ai_service.py#L47-L86)

章节来源
- [app/services/ai_service.py:47-86](file://app/services/ai_service.py#L47-L86)

### Wiki构建流程与状态机
- 文章生成
  - 从源文档抽取纯文本，截断安全上限，拼装系统提示与用户模板，调用LLM生成JSON结构化结果，解析为草稿对象。
  - 去重slug生成，插入或更新文章记录，落盘为Markdown文件。
- 状态机
  - 知识库状态：IDLE → BUILDING → READY/FAILED
  - 源文档状态：PENDING → PROCESSING → PROCESSED/FAILED
- 错误恢复
  - 源文档处理异常捕获，记录错误消息，状态置为FAILED，不影响其他源文档。
  - 知识库级异常捕获，设置FAILED并持久化错误信息。

```mermaid
stateDiagram-v2
[*] --> IDLE
IDLE --> BUILDING : "开始构建"
BUILDING --> READY : "全部成功"
BUILDING --> FAILED : "部分或全部失败"
READY --> IDLE : "重新构建"
```

图表来源
- [app/models/ai_kb.py:8-12](file://app/models/ai_kb.py#L8-L12)
- [app/models/ai_kb.py:15-19](file://app/models/ai_kb.py#L15-L19)

章节来源
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:204-230](file://app/services/ai_service.py#L204-L230)
- [app/services/ai_service.py:296-311](file://app/services/ai_service.py#L296-L311)
- [app/services/ai_service.py:313-341](file://app/services/ai_service.py#L313-L341)
- [app/models/ai_kb.py:8-12](file://app/models/ai_kb.py#L8-L12)
- [app/models/ai_kb.py:15-19](file://app/models/ai_kb.py#L15-L19)

### 源文档处理管道
- 输入：AIKBSource（绑定知识库与文档）
- 处理：逐条拉取源文档，抽取纯文本，调用LLM生成草稿，入库与落盘
- 输出：AIKBArticle（含标题、别名、摘要、标签、正文、来源文档ID列表）

```mermaid
flowchart TD
Start(["开始"]) --> LoadSrc["加载源文档"]
LoadSrc --> Exists{"是否存在且未删除?"}
Exists -- 否 --> Fail["标记FAILED并记录错误"]
Exists -- 是 --> Extract["提取纯文本"]
Extract --> CallLLM["调用LLM生成草稿"]
CallLLM --> Upsert["upsert_article入库/落盘"]
Upsert --> Next{"还有源文档?"}
Next -- 是 --> LoadSrc
Next -- 否 --> Done(["结束"])
Fail --> Done
```

图表来源
- [app/services/ai_service.py:296-311](file://app/services/ai_service.py#L296-L311)
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:204-230](file://app/services/ai_service.py#L204-L230)

章节来源
- [app/services/ai_service.py:296-311](file://app/services/ai_service.py#L296-L311)
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:204-230](file://app/services/ai_service.py#L204-L230)

### 链接解析算法与跨文档引用
- 解析步骤
  - 清空旧链接表，构建标题/别名/slug索引（大小写不敏感去重）
  - 扫描所有文章正文中的wikilink，查找目标文章，生成出站/入站链接
  - 统计解析数与红链数（未命中的占位符）
- 解析器
  - 提供resolver闭包，将[[Target]]映射为slug或None
  - 蓝图层渲染时，将占位锚点替换为实际URL

```mermaid
flowchart TD
Init["清空链接表"] --> BuildIdx["构建标题/别名/slug索引"]
BuildIdx --> Scan["遍历所有文章正文"]
Scan --> Collect["collect_wikilinks收集目标"]
Collect --> Lookup{"在索引中找到?"}
Lookup -- 是 --> CreateLink["创建链接(from,to)"]
Lookup -- 否 --> Redlink["记录红链"]
CreateLink --> NextArt{"还有文章?"}
Redlink --> NextArt
NextArt -- 是 --> Scan
NextArt -- 否 --> Commit["提交事务"]
```

图表来源
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- [app/utils/markdown.py:69-87](file://app/utils/markdown.py#L69-L87)
- [app/blueprints/ai.py:182-191](file://app/blueprints/ai.py#L182-L191)

章节来源
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- [app/utils/markdown.py:69-87](file://app/utils/markdown.py#L69-L87)
- [app/blueprints/ai.py:182-191](file://app/blueprints/ai.py#L182-L191)

### RAG检索与问答（可选）
- 触发条件：知识库开启enable_rag
- 检索策略：关键词重排Top-N文章，拼接上下文后调用LLM回答
- 向量存储：预留ai_kb_chunks表与vector_id字段，嵌入模型与Chroma路径由配置提供（需安装可选依赖）

```mermaid
sequenceDiagram
participant Client as "客户端"
participant BP as "蓝图 : ai.py"
participant Svc as "服务 : ai_service.py"
participant DB as "数据库 : ai_kb.py"
participant LLM as "LLM客户端"
Client->>BP : "POST /ai/<id>/chat"
BP->>Svc : "chat_with_wiki(ai_kb, question)"
Svc->>DB : "查询文章列表"
DB-->>Svc : "文章集合"
Svc->>Svc : "关键词重排Top-N"
Svc->>LLM : "chat(系统提示+上下文+问题)"
LLM-->>Svc : "回答文本"
Svc-->>BP : "回答"
BP-->>Client : "JSON响应"
```

图表来源
- [app/blueprints/ai.py:265-279](file://app/blueprints/ai.py#L265-L279)
- [app/services/ai_service.py:391-408](file://app/services/ai_service.py#L391-L408)
- [app/config.py:44-47](file://app/config.py#L44-L47)
- [app/models/ai_kb.py:110-121](file://app/models/ai_kb.py#L110-L121)

章节来源
- [app/services/ai_service.py:391-408](file://app/services/ai_service.py#L391-L408)
- [app/blueprints/ai.py:265-279](file://app/blueprints/ai.py#L265-L279)
- [app/config.py:44-47](file://app/config.py#L44-L47)
- [app/models/ai_kb.py:110-121](file://app/models/ai_kb.py#L110-L121)

### 增量更新与重生机制
- 单篇文章重生：根据文章首个源文档重建条目，保持slug不变，更新数据库与文件
- 全量重建：可选择仅处理待处理/失败的源文档，或重置状态后全量重建

```mermaid
sequenceDiagram
participant Client as "客户端"
participant BP as "蓝图 : ai.py"
participant Svc as "服务 : ai_service.py"
participant DB as "数据库 : ai_kb.py"
participant LLM as "LLM客户端"
participant FS as "文件系统"
Client->>BP : "POST /ai/<id>/wiki/<slug>/regenerate"
BP->>Svc : "regenerate_one_async(app, ai_kb_id, article_id)"
Svc->>DB : "设置状态 BUILDING"
Svc->>LLM : "chat(系统提示+用户提示)"
LLM-->>Svc : "JSON结构化输出"
Svc->>DB : "更新文章字段"
Svc->>FS : "_write_article_file(...)"
Svc->>Svc : "resolve_links(ai_kb)"
Svc->>DB : "设置状态 READY / 记录时间"
```

图表来源
- [app/blueprints/ai.py:239-248](file://app/blueprints/ai.py#L239-L248)
- [app/services/ai_service.py:347-381](file://app/services/ai_service.py#L347-L381)
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:204-230](file://app/services/ai_service.py#L204-L230)
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)

章节来源
- [app/blueprints/ai.py:239-248](file://app/blueprints/ai.py#L239-L248)
- [app/services/ai_service.py:347-381](file://app/services/ai_service.py#L347-L381)

### 蓝图层交互与中间件集成
- 权限控制：仅知识库拥有者或超级管理员可操作AI知识库
- 状态查询：提供JSON接口返回知识库状态、错误、最后构建时间、源文档计数与文章数量
- 中间件：登录、CSRF、数据库扩展在应用工厂中注册

```mermaid
graph LR
A["蓝图: ai.py"] --> B["权限校验: 仅拥有者/超级管理员"]
A --> C["状态查询: /ai/<id>/status -> JSON"]
A --> D["中间件: 登录/CSRF/数据库"]
```

图表来源
- [app/blueprints/ai.py:18-25](file://app/blueprints/ai.py#L18-L25)
- [app/blueprints/ai.py:159-173](file://app/blueprints/ai.py#L159-L173)
- [app/__init__.py:39-54](file://app/__init__.py#L39-L54)
- [app/extensions.py:1-17](file://app/extensions.py#L1-L17)

章节来源
- [app/blueprints/ai.py:18-25](file://app/blueprints/ai.py#L18-L25)
- [app/blueprints/ai.py:159-173](file://app/blueprints/ai.py#L159-L173)
- [app/__init__.py:39-54](file://app/__init__.py#L39-L54)
- [app/extensions.py:1-17](file://app/extensions.py#L1-L17)

## 依赖分析
- 运行时依赖：Flask、SQLAlchemy、OpenAI SDK、python-slugify、markdown、bleach等
- 可选依赖：当启用RAG时需要chromadb与tiktoken（见配置与注释）
- 服务层与蓝图层解耦：蓝图仅负责路由与权限，业务逻辑集中在服务层

```mermaid
graph TB
REQ["requirements.txt"] --> FLASK["Flask"]
REQ --> SA["SQLAlchemy"]
REQ --> OA["openai"]
REQ --> SLUG["python-slugify"]
REQ --> MD["markdown"]
REQ --> BL["bleach"]
REQ -. 可选 .-> CHROMA["chromadb"]
REQ -. 可选 .-> TIK["tiktoken"]
```

图表来源
- [requirements.txt:1-21](file://requirements.txt#L1-L21)

章节来源
- [requirements.txt:1-21](file://requirements.txt#L1-L21)
- [app/config.py:44-47](file://app/config.py#L44-L47)

## 性能考虑
- 文本截断与安全上限：对源文档纯文本进行长度限制，降低LLM输入成本与风险
- 惰性初始化：LLM客户端按需创建，避免全局初始化开销
- 文件落盘：文章以独立Markdown文件存储，便于静态化与CDN加速
- 索引去重：wikilink解析前构建大小写不敏感索引，减少重复计算
- 并发与后台任务：使用后台线程执行构建，避免阻塞请求；失败不影响其他任务
- 可选RAG：仅在enable_rag开启时引入向量化与Chroma存储，按需启用

章节来源
- [app/services/ai_service.py:147-161](file://app/services/ai_service.py#L147-L161)
- [app/services/ai_service.py:62-70](file://app/services/ai_service.py#L62-L70)
- [app/services/ai_service.py:196-202](file://app/services/ai_service.py#L196-L202)
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- [app/services/ai_service.py:313-341](file://app/services/ai_service.py#L313-L341)
- [app/config.py:44-47](file://app/config.py#L44-L47)

## 故障排除指南
- LLM SDK未安装
  - 现象：初始化LLM客户端时报运行时错误
  - 处理：安装openai依赖或检查环境变量
  - 参考路径：[app/services/ai_service.py:67-69](file://app/services/ai_service.py#L67-L69)
- 源文档不存在或已删除
  - 现象：构建阶段状态置为FAILED并记录错误
  - 处理：确认源文档状态，重新加入或修复文档
  - 参考路径：[app/services/ai_service.py:302-303](file://app/services/ai_service.py#L302-L303)
- 红链过多
  - 现象：wikilink未解析为目标文章
  - 处理：检查目标标题/别名是否正确，必要时手动修正
  - 参考路径：[app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- 知识库构建失败
  - 现象：状态停留在BUILDING或切换为FAILED
  - 处理：查看错误消息，重试或清理失败状态后全量重建
  - 参考路径：[app/services/ai_service.py:338-341](file://app/services/ai_service.py#L338-L341)
- RAG不可用
  - 现象：启用RAG后仍为纯文本问答
  - 处理：安装chromadb与tiktoken，配置EMBEDDING_MODEL与CHROMA_PATH
  - 参考路径：[requirements.txt:19-21](file://requirements.txt#L19-L21)，[app/config.py:44-47](file://app/config.py#L44-L47)

章节来源
- [app/services/ai_service.py:67-69](file://app/services/ai_service.py#L67-L69)
- [app/services/ai_service.py:302-303](file://app/services/ai_service.py#L302-L303)
- [app/services/ai_service.py:251-278](file://app/services/ai_service.py#L251-L278)
- [app/services/ai_service.py:338-341](file://app/services/ai_service.py#L338-L341)
- [requirements.txt:19-21](file://requirements.txt#L19-L21)
- [app/config.py:44-47](file://app/config.py#L44-L47)

## 结论
本服务层以Karpathy LLM Wiki方法为核心，结合可选RAG增强，提供了从源文档到可导航知识图谱的完整链路。通过清晰的状态机、健壮的错误恢复、可扩展的LLM封装与后台异步任务，既满足纯文本知识库场景，也为未来向量检索与大规模扩展打下基础。蓝图层与服务层职责分离，便于维护与演进。

## 附录

### 服务层API接口文档（蓝图层）
- 获取状态
  - 方法：GET
  - 路径：/ai/<ai_kb_id>/status
  - 返回：JSON，包含status、error、last_built_at、sources计数、articles数量
  - 权限：登录用户
  - 参考路径：[app/blueprints/ai.py:159-173](file://app/blueprints/ai.py#L159-L173)
- 启动构建
  - 方法：POST
  - 路径：/ai/<ai_kb_id>/build
  - 参数：scope（默认仅待处理，传all则重置为PENDING后全量）
  - 返回：重定向至详情页
  - 权限：登录用户（拥有者或超级管理员）
  - 参考路径：[app/blueprints/ai.py:143-156](file://app/blueprints/ai.py#L143-L156)
- 文章重生
  - 方法：POST
  - 路径：/ai/<ai_kb_id>/wiki/<slug>/regenerate
  - 返回：重定向至文章详情
  - 权限：登录用户（拥有者或超级管理员）
  - 参考路径：[app/blueprints/ai.py:239-248](file://app/blueprints/ai.py#L239-L248)
- 聊天问答（可选）
  - 方法：GET/POST
  - 路径：/ai/<ai_kb_id>/chat
  - POST参数：q（问题）
  - 返回：JSON，包含ok与answer或error
  - 权限：登录用户
  - 参考路径：[app/blueprints/ai.py:265-279](file://app/blueprints/ai.py#L265-L279)

章节来源
- [app/blueprints/ai.py:159-173](file://app/blueprints/ai.py#L159-L173)
- [app/blueprints/ai.py:143-156](file://app/blueprints/ai.py#L143-L156)
- [app/blueprints/ai.py:239-248](file://app/blueprints/ai.py#L239-L248)
- [app/blueprints/ai.py:265-279](file://app/blueprints/ai.py#L265-L279)

### 关键数据模型与关系
```mermaid
erDiagram
AI_KNOWLEDGE_BASES {
int id PK
int owner_id FK
string name
string description
string chat_model
boolean enable_rag
string status
datetime last_built_at
string error_msg
}
AI_KB_SOURCES {
int id PK
int ai_kb_id FK
int doc_id FK
string status
string err_msg
}
AI_KB_ARTICLES {
int id PK
int ai_kb_id FK
string title
string slug UK
string summary
text tags_json
text aliases_json
text content_md
text source_doc_ids_json
}
AI_KB_LINKS {
int id PK
int ai_kb_id FK
int from_article_id FK
int to_article_id FK
string anchor_text
}
AI_KB_CHUNKS {
int id PK
int ai_kb_id FK
int article_id FK
int chunk_idx
text content
string vector_id
}
AI_KNOWLEDGE_BASES ||--o{ AI_KB_SOURCES : "包含"
AI_KNOWLEDGE_BASES ||--o{ AI_KB_ARTICLES : "包含"
AI_KB_ARTICLES ||--o{ AI_KB_LINKS : "产生"
AI_KNOWLEDGE_BASES ||--o{ AI_KB_CHUNKS : "包含"
AI_KB_ARTICLES ||--o{ AI_KB_CHUNKS : "包含"
```

图表来源
- [app/models/ai_kb.py:22-44](file://app/models/ai_kb.py#L22-L44)
- [app/models/ai_kb.py:46-64](file://app/models/ai_kb.py#L46-L64)
- [app/models/ai_kb.py:66-91](file://app/models/ai_kb.py#L66-L91)
- [app/models/ai_kb.py:93-108](file://app/models/ai_kb.py#L93-L108)
- [app/models/ai_kb.py:110-121](file://app/models/ai_kb.py#L110-L121)