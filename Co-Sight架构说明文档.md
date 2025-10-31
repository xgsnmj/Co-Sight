# Co-Sight 项目架构说明文档

## 一、项目概述

### 1.1 项目简介
Co-Sight 是一个基于多智能体协作的AI研究分析系统，能够通过智能任务规划、自动执行和结果验证，生成高质量的研究报告。系统采用"规划-执行-总结"的三阶段工作流程，结合多种AI模型和工具，实现复杂任务的自动化处理。

### 1.2 核心特性
- **多智能体协作**：规划智能体（Planner）+ 执行智能体（Actor）协同工作
- **DAG任务调度**：支持依赖关系的并行任务执行
- **多模型支持**：可为不同角色配置不同的LLM模型
- **丰富的工具集**：集成搜索、文件处理、代码执行、图像/音视频分析等20+工具
- **实时通信**：基于WebSocket的流式数据推送
- **模块化设计**：清晰的分层架构，易于扩展

### 1.3 技术栈
- **后端框架**：FastAPI + Uvicorn
- **AI框架**：lagent（智能体框架）
- **LLM接口**：OpenAI兼容接口
- **并发处理**：Python Threading + asyncio
- **Web自动化**：browser-use
- **搜索引擎**：Tavily、Google、Baidu、Wikipedia
- **数据处理**：Pandas、Plotly、minify-html
- **通信协议**：WebSocket、HTTP REST API

---

## 二、系统架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 Web 界面                              │
│                    (http://localhost:7788/cosight/)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Web服务层                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 用户管理路由  │  │ WebSocket路由 │  │ 搜索路由     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      核心业务层 (CoSight)                         │
│  ┌────────────────────────────────────────────────────┐         │
│  │  任务编排引擎 (CoSight.execute)                      │         │
│  │  - 持续监控可执行步骤                                │         │
│  │  - 并发执行（最多5个线程）                           │         │
│  │  - 动态依赖解析                                      │         │
│  └────────────────────────────────────────────────────┘         │
│                           │                                      │
│  ┌────────────────────────┼────────────────────────┐            │
│  │                        │                        │            │
│  ▼                        ▼                        ▼            │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│ │ 规划智能体    │  │ 执行智能体    │  │ 工具调用层    │           │
│ │ (Planner)    │  │ (Actor)      │  │ (Tools)      │           │
│ │              │  │              │  │              │           │
│ │ - 创建计划    │  │ - 执行步骤    │  │ - 20+工具     │           │
│ │ - 更新计划    │  │ - 标记状态    │  │ - MCP扩展     │           │
│ │ - 生成总结    │  │ - 工具调用    │  │              │           │
│ └──────────────┘  └──────────────┘  └──────────────┘           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    任务管理层 (TaskManager)                       │
│  ┌────────────────────────────────────────────────────┐         │
│  │  Plan对象 (DAG结构)                                  │         │
│  │  - steps: 步骤列表                                  │         │
│  │  - dependencies: 依赖关系 {step_index: [deps]}     │         │
│  │  - step_statuses: 步骤状态                          │         │
│  │  - step_notes: 执行结果                             │         │
│  │  - get_ready_steps(): 获取可执行步骤                │         │
│  └────────────────────────────────────────────────────┘         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    LLM模型层 (llm.py)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 规划模型      │  │ 执行模型      │  │ 工具模型      │          │
│  │ llm_for_plan │  │ llm_for_act  │  │ llm_for_tool │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │ 视觉模型      │  │ 可信度模型    │                            │
│  │llm_for_vision│  │llm_credibility│                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块说明

#### 2.2.1 项目目录结构
```
Co-Sight/
├── CoSight.py                      # 核心引擎入口
├── llm.py                          # LLM模型配置
├── requirements.txt                # 依赖清单
├── .env                           # 环境变量配置
├── config/                        # 配置管理
│   └── config.py                  # 模型配置函数
├── app/
│   ├── cosight/                   # 核心业务模块
│   │   ├── agent/                 # 智能体实现
│   │   │   ├── planner/          # 规划智能体
│   │   │   │   ├── task_plannr_agent.py    # 规划智能体
│   │   │   │   ├── instance/               # 智能体实例
│   │   │   │   └── prompt/                 # Prompt模板
│   │   │   ├── actor/            # 执行智能体
│   │   │   │   ├── task_actor_agent.py     # 执行智能体
│   │   │   │   ├── instance/               # 智能体实例
│   │   │   │   └── prompt/                 # Prompt模板
│   │   │   └── base/             # 基础类和工具映射
│   │   ├── task/                  # 任务管理
│   │   │   ├── task_manager.py    # 任务管理器（线程安全）
│   │   │   ├── todolist.py        # Plan对象（DAG结构）
│   │   │   ├── plan_report_manager.py      # 事件管理
│   │   │   └── time_record_util.py         # 时间记录
│   │   ├── tool/                  # 工具集成
│   │   │   ├── act_toolkit.py            # 任务标记工具
│   │   │   ├── file_toolkit.py           # 文件操作
│   │   │   ├── code_toolkit.py           # 代码执行
│   │   │   ├── search_toolkit.py         # 多源搜索
│   │   │   ├── web_util.py               # 浏览器自动化
│   │   │   ├── image_analysis_toolkit.py # 图像分析
│   │   │   ├── video_analysis_toolkit.py # 视频分析
│   │   │   ├── audio_toolkit.py          # 音频识别
│   │   │   ├── document_processing_toolkit.py  # 文档处理
│   │   │   ├── html_visualization_toolkit.py   # HTML报告生成
│   │   │   └── deep_search/              # 深度搜索模块
│   │   └── llm/                   # LLM封装
│   │       └── chat_llm.py        # ChatLLM类
│   ├── agent_dispatcher/          # 智能体调度框架
│   └── common/                    # 公共工具
│       └── logger_util.py         # 日志工具
├── cosight_server/                # Web服务
│   └── deep_research/             # 研究服务
│       ├── main.py                # FastAPI主入口
│       ├── service.py             # 业务服务
│       ├── entity.py              # 数据实体
│       ├── routers/               # 路由模块
│       │   ├── websocket_manager.py  # WebSocket路由
│       │   ├── chat_manager.py       # 聊天路由
│       │   ├── search.py             # 搜索路由
│       │   └── user_manager.py       # 用户路由
│       └── services/              # 服务层
│           ├── credibility_analyzer.py    # 可信度分析
│           └── i18n_service.py            # 国际化
├── work_space/                    # 工作区（运行时生成）
│   └── work_space_20250131_143052_123456/
├── upload_files/                  # 文件上传目录
└── logs/                          # 日志目录
```

---

## 三、核心组件详解

### 3.1 CoSight 核心引擎 (CoSight.py)

**功能**：系统的核心调度引擎，负责任务的整体编排和执行。

**关键代码位置**：`CoSight.py:34-154`

#### 3.1.1 初始化流程
```python
# CoSight.py:35-44
def __init__(self, plan_llm, act_llm, tool_llm, vision_llm, work_space_path, message_uuid):
    # 1. 设置工作空间路径
    self.work_space_path = work_space_path
    # 2. 生成唯一的计划ID
    self.plan_id = message_uuid or f"plan_{int(time.time())}"
    # 3. 创建Plan对象并注册到TaskManager
    self.plan = Plan()
    TaskManager.set_plan(self.plan_id, self.plan)
    # 4. 创建规划智能体
    self.task_planner_agent = TaskPlannerAgent(...)
    # 5. 存储各类LLM模型
```

#### 3.1.2 执行流程 (execute方法)
```python
# CoSight.py:46-91
def execute(self, question, output_format=""):
    # 阶段1: 创建计划（最多重试3次）
    while not self.plan.get_ready_steps() and retry_count < 3:
        create_result = self.task_planner_agent.create_plan(create_task, output_format)
        retry_count += 1

    # 阶段2: 持续监控并执行任务
    active_threads = {}  # 存储活跃线程
    while True:
        # 2.1 获取可执行步骤
        ready_steps = self.plan.get_ready_steps()

        # 2.2 为新步骤启动执行线程
        for step_index in ready_steps:
            if step_index not in active_threads:
                thread = Thread(target=self._execute_single_step, args=(question, step_index))
                thread.start()
                active_threads[step_index] = thread

        # 2.3 清理已完成的线程
        for step_index, thread in active_threads.items():
            if not thread.is_alive():
                completed_steps.append(step_index)

        # 2.4 退出条件：无活跃线程且无可执行步骤
        if not active_threads and not ready_steps:
            break

    # 阶段3: 生成最终总结
    return self.task_planner_agent.finalize_plan(question, output_format)
```

**设计亮点**：
1. **动态并发**：根据DAG依赖关系动态创建执行线程
2. **实时监控**：持续检查任务状态，无需等待所有任务完成
3. **容错机制**：创建计划失败时自动重试

---

### 3.2 智能体系统 (Agent)

#### 3.2.1 规划智能体 (TaskPlannerAgent)

**文件位置**：`app/cosight/agent/planner/task_plannr_agent.py`

**核心职责**：
1. 根据用户问题创建执行计划
2. 在执行过程中更新计划
3. 汇总所有步骤生成最终报告

**关键方法**：
```python
# task_plannr_agent.py:40-44
def create_plan(self, question, output_format=""):
    """创建初始执行计划"""
    self.history.append({"role": "system", "content": planner_system_prompt(question)})
    self.history.append({"role": "user", "content": planner_create_plan_prompt(question, output_format)})
    return self.execute(self.history, max_iteration=1)

# task_plannr_agent.py:46-50
def re_plan(self, question, output_format=""):
    """根据当前进度重新规划"""
    self.history.append({"role": "user", "content": planner_re_plan_prompt(...)})
    return self.execute(self.history, max_iteration=1)

# task_plannr_agent.py:52-67
def finalize_plan(self, question, output_format=""):
    """生成最终总结报告"""
    result = self.llm.chat_to_llm(self.history)
    self.plan.set_plan_result(result)
    plan_report_event_manager.publish("plan_result", self.plan)
    return result
```

**可用工具**：
- `create_plan`：创建新计划
- `update_plan`：更新现有计划
- `terminate`：终止执行

#### 3.2.2 执行智能体 (TaskActorAgent)

**文件位置**：`app/cosight/agent/actor/task_actor_agent.py`

**核心职责**：
1. 执行具体的任务步骤
2. 调用各种工具完成任务
3. 更新步骤状态和结果

**关键方法**：
```python
# task_actor_agent.py:142-172
def act(self, question, step_index):
    """执行单个任务步骤"""
    # 1. 标记步骤为进行中
    self.plan.mark_step(step_index, step_status="in_progress")

    # 2. 生成任务提示词
    task_prompt = actor_execute_task_prompt_zh(question, step_index, self.plan, self.work_space_path)

    # 3. 执行任务
    try:
        result = self.execute(self.history, step_index=step_index)
        # 4. 标记为完成
        self.plan.mark_step(step_index, step_status="completed", step_notes=str(result))
    except Exception as e:
        # 5. 异常处理：标记为阻塞
        self.plan.mark_step(step_index, step_status="blocked", step_notes=str(e))
```

**集成工具** (20+工具)：
```python
# task_actor_agent.py:98-126
all_functions = {
    # 任务管理
    "mark_step": act_toolkit.mark_step,

    # 搜索工具
    "search_baidu": search_baidu,
    "search_google": search_toolkit.search_google,
    "search_wiki": search_toolkit.search_wiki,
    "tavily_search": search_toolkit.tavily_search,

    # 代码执行
    "execute_code": code_toolkit.execute_code,

    # 文件操作
    "file_saver": file_toolkit.file_saver,
    "file_read": file_toolkit.file_read,
    "file_str_replace": file_toolkit.file_str_replace,
    "file_find_in_content": file_toolkit.file_find_in_content,

    # 多模态工具
    "ask_question_about_image": image_toolkit.ask_question_about_image,
    "ask_question_about_video": video_toolkit.ask_question_about_video,
    "audio_recognition": audio_toolkit.speech_to_text,

    # 网页处理
    "fetch_website_content": fetch_website_content,
    "fetch_website_content_with_images": fetch_website_content_with_images,
    "fetch_website_images_only": fetch_website_images_only,

    # 文档处理
    "extract_document_content": doc_toolkit.extract_document_content,

    # HTML报告生成
    "create_html_report": html_toolkit.create_html_report,
}
```

---

### 3.3 任务管理系统 (Task)

#### 3.3.1 TaskManager (任务管理器)

**文件位置**：`app/cosight/task/task_manager.py`

**功能**：全局任务管理，线程安全的Plan对象存储。

**数据结构**：
```python
# task_manager.py:19-24
class TaskManager:
    _lock = Lock()  # 线程锁
    plans = {}  # {plan_id: Plan对象}
    plan_to_id = {}  # {Plan内存地址: plan_id}
    running_plans = set()  # 运行中的计划集合
```

**关键方法**：
- `set_plan(plan_id, plan)`：注册计划
- `get_plan(plan_id)`：获取计划
- `is_running(plan_id)`：检查是否运行中
- `mark_running(plan_id)`：标记为运行中
- `mark_completed(plan_id)`：标记为完成

#### 3.3.2 Plan对象 (DAG结构)

**文件位置**：`app/cosight/task/todolist.py`

**核心数据结构**：
```python
# todolist.py:30-49
class Plan:
    def __init__(self, title, steps, dependencies, work_space_path):
        self.title = title  # 计划标题
        self.steps = []  # 步骤列表（字符串）
        self.step_statuses = {}  # {step: "not_started"|"in_progress"|"completed"|"blocked"}
        self.step_notes = {}  # {step: 执行结果}
        self.step_details = {}  # {step: 详细信息}
        self.step_files = {}  # {step: 生成的文件}
        self.step_tool_calls = {}  # {step: [工具调用记录]}
        self.dependencies = {}  # {step_index: [依赖的step_index列表]}
        self.result = ""  # 最终结果
        self.work_space_path = work_space_path
```

**关键方法**：

1. **获取可执行步骤** (最核心的方法)
```python
# todolist.py:57-75
def get_ready_steps(self) -> List[int]:
    """获取所有前置依赖都已完成的步骤"""
    ready_steps = []
    for step_index in range(len(self.steps)):
        # 获取该步骤的所有依赖
        dependencies = self.dependencies.get(step_index, [])

        # 检查所有依赖是否都已完成
        if all(self.step_statuses.get(self.steps[int(dep)]) not in ["not_started","in_progress"]
               for dep in dependencies):
            # 检查步骤本身是否未开始
            if self.step_statuses.get(self.steps[step_index]) == "not_started":
                ready_steps.append(step_index)

    return ready_steps
```

2. **更新计划**
```python
# todolist.py:77-129
def update(self, title, steps, dependencies):
    """更新计划，保留已完成步骤的状态"""
    # 保留已开始的步骤
    # 添加新步骤
    # 更新依赖关系
```

3. **标记步骤状态**
```python
# todolist.py:131-160
def mark_step(self, step_index, step_status, step_notes):
    """标记步骤状态和执行结果"""
    step = self.steps[step_index]
    if step_status is not None:
        self.step_statuses[step] = step_status
    if step_notes is not None:
        self.step_notes[step] = step_notes
```

4. **依赖关系规范化**
```python
# todolist.py:210-234
def _normalize_dependencies(self, dependencies):
    """将1基编号转换为0基编号"""
    # 处理JSON传入的字符串key
    # 判断是否需要整体减1
    # 自动适配不同的编号系统
```

---

### 3.4 LLM模型管理 (llm.py)

**文件位置**：`llm.py` 和 `config/config.py`

#### 3.4.1 模型配置策略

**分层配置**：
1. **基础配置** (`.env`文件)：
   - `API_KEY`, `API_BASE_URL`, `MODEL_NAME`
   - `MAX_TOKENS`, `TEMPERATURE`, `PROXY`

2. **专用配置** (可选)：
   - 规划模型：`PLAN_*` 系列环境变量
   - 执行模型：`ACT_*` 系列环境变量
   - 工具模型：`TOOL_*` 系列环境变量
   - 视觉模型：`VISION_*` 系列环境变量
   - 可信度模型：`CREDIBILITY_*` 系列环境变量
   - 浏览器模型：`BROWSER_*` 系列环境变量

#### 3.4.2 配置读取逻辑

```python
# config/config.py:41-61
def get_plan_model_config():
    """获取规划模型配置，如果未设置则退回到基础配置"""
    plan_api_key = os.environ.get("PLAN_API_KEY")
    plan_base_url = os.environ.get("PLAN_API_BASE_URL")
    model_name = os.environ.get("PLAN_MODEL_NAME")

    # 如果三个必要字段都存在，则使用专用配置
    if not (plan_api_key and plan_base_url and model_name):
        return get_model_config()  # 退回基础配置

    # 返回专用配置
    return {
        "api_key": plan_api_key,
        "base_url": plan_base_url,
        "model": model_name,
        "max_tokens": ...,
        "temperature": ...,
        "proxy": ...
    }
```

#### 3.4.3 模型初始化

```python
# llm.py:23-54
def set_model(model_config):
    """初始化LLM客户端"""
    # 1. 创建HTTP客户端（支持代理和自定义header）
    http_client = httpx.Client(
        headers={'Authorization': model_config['api_key']},
        proxy=model_config['proxy'],
        verify=False
    )

    # 2. 创建OpenAI客户端
    openai_llm = OpenAI(
        base_url=model_config['base_url'],
        api_key=model_config['api_key'],
        http_client=http_client
    )

    # 3. 封装为ChatLLM对象
    return ChatLLM(
        model=model_config['model'],
        client=openai_llm,
        max_tokens=model_config['max_tokens'],
        temperature=model_config['temperature']
    )

# llm.py:57-76
# 初始化所有模型
llm_for_plan = set_model(get_plan_model_config())
llm_for_act = set_model(get_act_model_config())
llm_for_tool = set_model(get_tool_model_config())
llm_for_vision = set_model(get_vision_model_config())
llm_for_credibility = set_model(get_credibility_model_config())
```

---

### 3.5 Web服务层 (cosight_server)

#### 3.5.1 服务架构

**主入口**：`cosight_server/deep_research/main.py:223`

**服务端口**：`7788` (可配置)

**访问地址**：`http://localhost:7788/cosight/`

#### 3.5.2 路由模块

**文件位置**：`cosight_server/deep_research/routers/`

```python
# main.py:205-210
app.include_router(userRouter, prefix="/api")
app.include_router(searchRouter, prefix="/api")
app.include_router(wsRouter, prefix="/chatbot-api")
app.include_router(commonRouter, prefix="/api")
app.include_router(chatRouter, prefix="/chatbot-api")
app.include_router(feedbackRouter, prefix="/chatbot-api")
```

**路由列表**：
1. **用户管理** (`userRouter`)：用户认证和管理
2. **搜索服务** (`searchRouter`)：搜索功能
3. **WebSocket** (`wsRouter`)：实时通信
4. **通用接口** (`commonRouter`)：通用API
5. **聊天管理** (`chatRouter`)：对话管理
6. **反馈** (`feedbackRouter`)：用户反馈

#### 3.5.3 WebSocket实时通信

**功能**：流式推送任务执行进度和结果

**事件类型**：
- `plan_process`：任务进度更新
- `plan_result`：最终结果

**实现机制**：
```python
# app/cosight/task/plan_report_manager.py (推测)
class PlanReportEventManager:
    def publish(self, event_type, plan):
        """发布事件到WebSocket客户端"""
        # 将Plan对象序列化
        # 推送到已连接的WebSocket客户端
```

#### 3.5.4 静态资源挂载

```python
# main.py:151-154
# 挂载文件上传目录
app.mount("/api/upload_files", StaticFiles(directory="upload_files"))

# 挂载工作空间目录（运行时生成的文件）
app.mount("/api/work_space", StaticFiles(directory="work_space"))

# 挂载前端页面
app.mount("/cosight", StaticFiles(directory="web", html=True))
```

---

## 四、业务流程详解

### 4.1 完整执行流程

```
用户提交问题
    ↓
[1. 规划阶段]
    ├─ TaskPlannerAgent.create_plan()
    ├─ LLM生成执行计划
    ├─ 解析为Plan对象（title, steps, dependencies）
    └─ 注册到TaskManager
    ↓
[2. 执行阶段]
    ├─ CoSight.execute() 持续监控
    ├─ Plan.get_ready_steps() 获取可执行步骤
    │   └─ 检查依赖关系，返回所有ready的步骤
    ├─ 为每个ready步骤创建执行线程
    │   ├─ Thread(target=_execute_single_step)
    │   └─ TaskActorAgent.act(step_index)
    │       ├─ 标记步骤为 in_progress
    │       ├─ LLM决策需要使用的工具
    │       ├─ 调用工具（搜索、文件、代码等）
    │       ├─ 获取工具结果
    │       └─ 标记步骤为 completed/blocked
    ├─ 清理已完成线程
    └─ 重复直到所有步骤完成
    ↓
[3. 总结阶段]
    ├─ TaskPlannerAgent.finalize_plan()
    ├─ LLM汇总所有步骤结果
    ├─ 生成最终报告
    └─ 返回给用户
```

### 4.2 DAG依赖解析示例

假设有如下计划：
```json
{
  "steps": ["搜索资料", "分析数据", "生成图表", "撰写报告"],
  "dependencies": {
    "1": [],        // 步骤0无依赖，可立即执行
    "2": ["1"],     // 步骤1依赖步骤0
    "3": ["2"],     // 步骤2依赖步骤1
    "4": ["2", "3"] // 步骤3依赖步骤1和2
  }
}
```

**执行时间线**：
```
t0: ready_steps = [0] → 启动线程执行步骤0
t1: 步骤0完成 → ready_steps = [1] → 启动线程执行步骤1
t2: 步骤1完成 → ready_steps = [2] → 启动线程执行步骤2
t3: 步骤2完成 → ready_steps = [3] → 启动线程执行步骤3
    （步骤1和2都完成了，步骤3的依赖满足）
t4: 步骤3完成 → ready_steps = [] → 结束
```

### 4.3 并发执行示例

假设有如下计划（多个独立分支）：
```json
{
  "steps": ["搜索中兴", "搜索华为", "分析中兴", "分析华为", "对比报告"],
  "dependencies": {
    "0": [],        // 步骤0无依赖
    "1": [],        // 步骤1无依赖
    "2": ["0"],     // 步骤2依赖步骤0
    "3": ["1"],     // 步骤3依赖步骤1
    "4": ["2", "3"] // 步骤4依赖步骤2和3
  }
}
```

**执行时间线**：
```
t0: ready_steps = [0, 1]
    → 并发启动2个线程，同时执行步骤0和1
t1: 步骤0完成 → ready_steps = [2] → 启动线程执行步骤2
    步骤1还在执行中
t2: 步骤1完成 → ready_steps = [3] → 启动线程执行步骤3
    步骤2还在执行中
t3: 步骤2和3都完成 → ready_steps = [4] → 启动线程执行步骤4
t4: 步骤4完成 → 结束
```

**性能优势**：独立的步骤0和1可以并行执行，缩短总耗时。

---

## 五、核心工具详解

### 5.1 工具分类

#### 5.1.1 搜索类工具

| 工具名称 | 功能说明 | 数据源 |
|---------|---------|-------|
| `tavily_search` | AI优化的搜索引擎 | Tavily API |
| `search_google` | Google搜索 | Google Custom Search |
| `search_baidu` | 百度搜索 | Baidu API |
| `search_wiki` | 维基百科搜索 | Wikipedia API |
| `deep_search` | 深度搜索（多轮） | 多源聚合 |

**使用示例**：
```python
# 调用Tavily搜索
results = tavily_search(query="中兴通讯2024年财报", max_results=5)
# 返回：[{title, url, content, score}, ...]
```

#### 5.1.2 文件操作工具

| 工具名称 | 功能说明 |
|---------|---------|
| `file_saver` | 保存文件到工作空间 |
| `file_read` | 读取文件内容 |
| `file_str_replace` | 替换文件中的文本 |
| `file_find_in_content` | 在文件中查找内容 |

**文件路径处理**：
- 所有文件自动保存到 `work_space/work_space_时间戳/` 目录
- 前端可通过 `/api/work_space/work_space_时间戳/文件名` 访问

#### 5.1.3 代码执行工具

**工具**：`execute_code`

**功能**：在沙箱环境中执行Python代码

**实现**：
- 使用 `subprocess` 启动独立进程
- 支持标准库和常用数据分析库（pandas、numpy等）
- 超时控制和资源限制

**使用示例**：
```python
code = """
import pandas as pd
data = {'name': ['Alice', 'Bob'], 'age': [25, 30]}
df = pd.DataFrame(data)
print(df)
"""
result = execute_code(code, language="python")
```

#### 5.1.4 网页处理工具

| 工具名称 | 功能说明 |
|---------|---------|
| `fetch_website_content` | 获取网页纯文本内容 |
| `fetch_website_content_with_images` | 获取网页内容+图片信息 |
| `fetch_website_images_only` | 仅获取网页图片 |
| `browser_use` | 浏览器自动化（点击、输入等） |

**技术实现**：
- 基于 `requests` + `beautifulsoup` 解析静态页面
- 基于 `browser-use` 库处理动态页面
- 支持JavaScript渲染

#### 5.1.5 多模态工具

| 工具名称 | 功能说明 | 支持格式 |
|---------|---------|---------|
| `ask_question_about_image` | 图像理解和问答 | jpg, png, svg |
| `ask_question_about_video` | 视频理解和问答 | mp4, avi |
| `audio_recognition` | 语音转文字 | mp3, wav |

**实现原理**：
- 调用多模态LLM（如GPT-4 Vision）
- 支持本地文件和URL

#### 5.1.6 文档处理工具

**工具**：`extract_document_content`

**支持格式**：
- PDF文档
- Word文档（.docx）
- Excel表格（.xlsx）
- Markdown文件

**实现库**：
- `docx2markdown`：Word转Markdown
- `PyPDF2` / `pdfplumber`：PDF解析
- `pandas`：Excel处理

#### 5.1.7 HTML报告生成工具

**工具**：`create_html_report`

**功能**：
- 自动生成美观的HTML报告
- 支持多种图表（折线图、柱状图、饼图等）
- 基于Plotly实现交互式可视化

**使用示例**：
```python
html_file = create_html_report(
    title="中兴通讯分析报告",
    include_charts=True,
    chart_types=['line', 'bar'],
    output_filename="report.html"
)
```

### 5.2 工具扩展机制 (MCP)

**MCP (Model Context Protocol)**：工具扩展协议

**配置文件**：`config/mcp_server_config.json`

**扩展步骤**：
1. 在配置文件中定义新工具
2. 系统自动加载并注册到智能体
3. LLM可直接调用新工具

**示例配置**：
```json
{
  "mcpServers": {
    "custom_tool": {
      "command": "python",
      "args": ["path/to/tool.py"],
      "env": {}
    }
  }
}
```

---

## 六、数据流和状态管理

### 6.1 Plan对象状态流转

```
创建 (create_plan)
    ↓
步骤状态: not_started
    ↓
执行开始 (mark_step: in_progress)
    ↓
工具调用 (add_tool_call)
    ↓
执行结果 (mark_step: completed/blocked)
    ↓
最终总结 (finalize_plan)
    ↓
完成 (set_plan_result)
```

### 6.2 事件驱动架构

**事件管理器**：`plan_report_event_manager`

**事件类型**：
1. `plan_process`：任务进度变化
   - 触发时机：步骤状态改变时
   - 数据：完整的Plan对象

2. `plan_result`：任务最终完成
   - 触发时机：finalize_plan完成时
   - 数据：Plan对象 + 最终报告

**订阅方式**：
```python
# WebSocket客户端自动订阅
# 服务端通过WebSocket推送事件
```

### 6.3 工作空间管理

**目录结构**：
```
work_space/
├── work_space_20250131_143052_123456/  # 每次执行创建新目录
│   ├── report.html                     # 生成的HTML报告
│   ├── data.csv                        # 保存的数据文件
│   ├── chart.png                       # 生成的图表
│   └── analysis.md                     # 分析文档
└── work_space_20250131_150230_789012/  # 另一次执行
```

**文件访问**：
- 前端：`http://localhost:7788/api/work_space/work_space_时间戳/文件名`
- 后端：直接使用绝对路径

---

## 七、关键技术点

### 7.1 线程安全设计

**问题**：多线程并发修改Plan对象

**解决方案**：
```python
# task_manager.py:20
class TaskManager:
    _lock = Lock()  # 类级别线程锁

    @classmethod
    def set_plan(cls, plan_id, plan):
        with cls._lock:  # 使用上下文管理器自动加锁/解锁
            cls.plans[plan_id] = plan
```

### 7.2 DAG依赖解析算法

**核心算法**：`Plan.get_ready_steps()`

**时间复杂度**：O(n * m)，其中n为步骤数，m为平均依赖数

**优化点**：
1. 只返回 `not_started` 状态的步骤
2. 检查依赖时只关心 `completed` 状态
3. 支持多步骤并行

### 7.3 动态线程管理

**策略**：
- 不使用线程池，而是动态创建/销毁线程
- 每个步骤一个独立线程
- 通过`thread.is_alive()`检查线程状态

**优势**：
- 更灵活的并发控制
- 无需预设线程池大小
- 自动适应任务复杂度

### 7.4 Prompt工程

**位置**：
- 规划：`app/cosight/agent/planner/prompt/planner_prompt.py`
- 执行：`app/cosight/agent/actor/prompt/actor_prompt.py`

**设计原则**：
1. **结构化输出**：使用JSON格式返回
2. **Few-shot学习**：提供示例
3. **明确约束**：指定工具使用规则
4. **上下文管理**：合理控制history长度

### 7.5 错误处理和重试

**创建计划重试**：
```python
# CoSight.py:49-53
retry_count = 0
while not self.plan.get_ready_steps() and retry_count < 3:
    create_result = self.task_planner_agent.create_plan(...)
    retry_count += 1
```

**步骤执行容错**：
```python
# task_actor_agent.py:160-172
try:
    result = self.execute(self.history, step_index=step_index)
    self.plan.mark_step(step_index, step_status="completed", ...)
except Exception as e:
    self.plan.mark_step(step_index, step_status="blocked", ...)
```

---

## 八、部署和配置

### 8.1 环境要求

**Python版本**：3.11+

**系统要求**：
- RAM: 4GB+
- 磁盘: 1GB+
- 操作系统: Windows 11 / Linux / macOS

### 8.2 安装步骤

```bash
# 1. 克隆代码
git clone https://github.com/ZTE-AICloud/Co-Sight.git
cd Co-Sight

# 2. 安装依赖
pip install -r requirements.txt
# 或使用uv
uv sync

# 3. 配置环境变量
cp .env_template .env
# 编辑.env文件，填入API密钥和模型配置

# 4. 启动服务
python cosight_server/deep_research/main.py
```

### 8.3 配置说明

**必填配置** (`.env`文件)：
```bash
# 基础模型配置（必填）
API_KEY=sk-xxxxx
API_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o

# 可选参数
MAX_TOKENS=4096
TEMPERATURE=0.7
PROXY=http://proxy.example.com:8080
```

**专用模型配置** (可选)：
```bash
# 规划模型（可选，不填则使用基础配置）
PLAN_API_KEY=sk-xxxxx
PLAN_API_BASE_URL=https://api.openai.com/v1
PLAN_MODEL_NAME=gpt-4o
PLAN_MAX_TOKENS=4096
PLAN_TEMPERATURE=0.3

# 执行模型（可选）
ACT_API_KEY=sk-xxxxx
ACT_API_BASE_URL=https://api.openai.com/v1
ACT_MODEL_NAME=gpt-4o

# 工具模型（可选）
TOOL_API_KEY=sk-xxxxx
TOOL_API_BASE_URL=https://api.openai.com/v1
TOOL_MODEL_NAME=gpt-4o-mini

# 视觉模型（可选）
VISION_API_KEY=sk-xxxxx
VISION_API_BASE_URL=https://api.openai.com/v1
VISION_MODEL_NAME=gpt-4o
```

**工具配置**：
```bash
# Tavily搜索（可选）
TAVILY_API_KEY=tvly-xxxxx

# Google搜索（可选）
GOOGLE_API_KEY=AIza-xxxxx
SEARCH_ENGINE_ID=xxxxx
```

### 8.4 启动方式

**方式1：启动Web服务**（推荐）
```bash
python cosight_server/deep_research/main.py
# 访问 http://localhost:7788/cosight/
```

**方式2：直接调用核心引擎**
```python
from CoSight import CoSight
from llm import llm_for_plan, llm_for_act, llm_for_tool, llm_for_vision

cosight = CoSight(llm_for_plan, llm_for_act, llm_for_tool, llm_for_vision, work_space_path)
result = cosight.execute("帮我写一篇中兴通讯的分析报告")
print(result)
```

### 8.5 端口配置

**默认端口**：7788

**修改方式**：
1. 环境变量：设置 `search_port=8080`
2. 命令行参数：`python main.py --port 8080`

---

## 九、性能优化建议

### 9.1 并发优化

**当前**：无限制并发（可能导致资源耗尽）

**优化建议**：
```python
# CoSight.py:117
semaphore = Semaphore(5)  # 限制最多5个并发线程

def execute_step(step_index):
    semaphore.acquire()
    try:
        # 执行步骤
    finally:
        semaphore.release()
```

### 9.2 LLM调用优化

**策略**：
1. **缓存常见查询**：避免重复调用
2. **流式输出**：使用stream模式提升响应速度
3. **模型分级**：简单任务用小模型，复杂任务用大模型

### 9.3 工作空间清理

**问题**：每次执行都创建新目录，长期运行会占用大量磁盘

**解决方案**：
```python
# 定期清理超过30天的工作空间
import os
import time
import shutil

def cleanup_old_workspaces(days=30):
    for dirname in os.listdir('work_space'):
        path = os.path.join('work_space', dirname)
        if os.path.isdir(path):
            mtime = os.path.getmtime(path)
            if time.time() - mtime > days * 86400:
                shutil.rmtree(path)
```

---

## 十、扩展开发指南

### 10.1 添加新工具

**步骤**：

1. **创建工具类**：
```python
# app/cosight/tool/my_toolkit.py
class MyToolkit:
    def my_tool(self, param1: str, param2: int) -> str:
        """
        工具描述（会被LLM看到）

        Args:
            param1: 参数1说明
            param2: 参数2说明

        Returns:
            返回值说明
        """
        # 工具实现
        return f"处理结果: {param1} - {param2}"
```

2. **注册到执行智能体**：
```python
# app/cosight/agent/actor/task_actor_agent.py:98
from app.cosight.tool.my_toolkit import MyToolkit

my_toolkit = MyToolkit()
all_functions = {
    ...
    "my_tool": my_toolkit.my_tool,  # 添加到函数字典
}
```

3. **测试**：
```python
# LLM会自动调用新工具
result = cosight.execute("使用my_tool处理数据")
```

### 10.2 自定义智能体

**步骤**：

1. **继承BaseAgent**：
```python
from app.cosight.agent.base.base_agent import BaseAgent

class MyCustomAgent(BaseAgent):
    def __init__(self, agent_instance, llm, functions):
        super().__init__(agent_instance, llm, functions)

    def custom_method(self, input_data):
        # 自定义逻辑
        pass
```

2. **集成到CoSight**：
```python
# 在CoSight.__init__中添加
self.my_agent = MyCustomAgent(...)
```

### 10.3 添加新的LLM提供商

**步骤**：

1. **修改ChatLLM类**：
```python
# app/cosight/llm/chat_llm.py
class ChatLLM:
    def __init__(self, provider="openai", ...):
        if provider == "openai":
            self.client = OpenAI(...)
        elif provider == "anthropic":
            self.client = Anthropic(...)  # 新增
```

2. **更新配置函数**：
```python
# config/config.py
def get_model_config():
    provider = os.environ.get("LLM_PROVIDER", "openai")
    return {
        "provider": provider,
        ...
    }
```

---

## 十一、常见问题 (FAQ)

### 11.1 为什么有的步骤没有执行？

**原因**：依赖关系配置错误

**排查**：
1. 检查 `dependencies` 配置
2. 查看日志：`self.plan.format()` 显示依赖关系
3. 确认前置步骤已完成

### 11.2 如何调试工具调用？

**方法**：
```python
# 查看工具调用记录
logger.info(f"Tool calls: {plan.step_tool_calls}")

# 在工具函数中添加日志
def my_tool(param):
    logger.info(f"my_tool called with: {param}")
    result = ...
    logger.info(f"my_tool result: {result}")
    return result
```

### 11.3 如何提高生成报告的质量？

**建议**：
1. **优化Prompt**：提供更详细的任务描述和输出格式要求
2. **使用更强的模型**：为规划和总结阶段配置GPT-4
3. **增加验证步骤**：在计划中添加"审核"步骤
4. **提供示例**：在Prompt中加入优秀报告示例

### 11.4 如何处理长时间运行的任务？

**方案**：
1. **异步执行**：前端发起请求后立即返回，通过WebSocket接收结果
2. **任务持久化**：将Plan对象保存到数据库
3. **断点续传**：支持从中断的步骤继续执行

---

## 十二、总结

### 12.1 核心优势

1. **智能化**：基于LLM的自动任务规划和执行
2. **并行化**：DAG依赖管理，支持多步骤并发
3. **模块化**：清晰的分层架构，易于扩展
4. **灵活性**：多模型配置，适应不同场景
5. **工具丰富**：20+内置工具，支持MCP扩展

### 12.2 适用场景

- **研究报告生成**：自动收集资料、分析数据、撰写报告
- **数据分析**：多源数据采集、处理、可视化
- **内容创作**：基于多源信息的内容聚合和创作
- **竞品分析**：自动搜索、对比、生成分析报告

### 12.3 未来展望

**可能的优化方向**：
1. **增加人工干预节点**：关键步骤需要人工确认
2. **支持更多数据源**：数据库、API、文件系统
3. **改进错误处理**：自动重试、回滚机制
4. **增强可观测性**：详细的执行日志和可视化
5. **支持分布式部署**：多机协作，提升处理能力

---

## 附录

### A. 核心文件清单

| 文件路径 | 功能说明 | 重要程度 |
|---------|---------|----------|
| `CoSight.py` | 核心引擎，任务编排 | ⭐⭐⭐⭐⭐ |
| `llm.py` | LLM模型初始化 | ⭐⭐⭐⭐⭐ |
| `app/cosight/task/todolist.py` | Plan对象，DAG管理 | ⭐⭐⭐⭐⭐ |
| `app/cosight/agent/planner/task_plannr_agent.py` | 规划智能体 | ⭐⭐⭐⭐⭐ |
| `app/cosight/agent/actor/task_actor_agent.py` | 执行智能体 | ⭐⭐⭐⭐⭐ |
| `app/cosight/task/task_manager.py` | 任务管理器 | ⭐⭐⭐⭐ |
| `config/config.py` | 配置管理 | ⭐⭐⭐⭐ |
| `cosight_server/deep_research/main.py` | Web服务入口 | ⭐⭐⭐⭐ |
| `app/cosight/tool/*` | 工具集合 | ⭐⭐⭐ |

### B. 环境变量完整列表

**基础配置**：
- `API_KEY`
- `API_BASE_URL`
- `MODEL_NAME`
- `MAX_TOKENS`
- `TEMPERATURE`
- `PROXY`

**专用模型配置**：
- `PLAN_*` (6个)
- `ACT_*` (6个)
- `TOOL_*` (6个)
- `VISION_*` (6个)
- `CREDIBILITY_*` (6个)
- `BROWSER_*` (6个)

**工具配置**：
- `TAVILY_API_KEY`
- `GOOGLE_API_KEY`
- `SEARCH_ENGINE_ID`

**路径配置**：
- `WORKSPACE_PATH_ENV`
- `WEB_DIR_ENV`

### C. API接口列表

**REST API**：
- `POST /api/search`：搜索接口
- `GET /api/users`：用户信息
- `POST /chatbot-api/chat`：对话接口

**WebSocket**：
- `ws://localhost:7788/chatbot-api/ws`：实时通信

**静态资源**：
- `/api/work_space/:workspace/:file`：工作空间文件
- `/api/upload_files/:file`：上传文件
- `/cosight/`：前端页面

---

**文档版本**：v1.0
**最后更新**：2025-01-31
**作者**：Co-Sight架构分析
