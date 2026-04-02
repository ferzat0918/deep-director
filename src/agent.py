"""
TVC Director Deep Agent — 主入口
使用 deepagents 框架搭建的 "Showrunner + 3 Sub-agent" 流水线。

架构:
  Showrunner (主 Agent / 监制)
    ├── task("screenwriter") → 编剧 Sub-agent → plot_outline
    ├── task("copywriter")   → 文案 Sub-agent → copywriting
    ├── task("dp")           → 摄影指导 Sub-agent → visual_board
    └── 自我评估 → Pass / Fail (精准打回)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from src.prompts import (
    load_copywriter_prompt,
    load_dp_prompt,
    load_screenwriter_prompt,
    load_showrunner_prompt,
)

# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# 模型配置 — 双模型策略
# ---------------------------------------------------------------------------
# Web 前端(langgraph dev) 用 V3: 速度快、异步兼容
# 终端脚本(chat.py) 用 R1: 质量最高、阻塞式思考
#
# 可通过环境变量覆盖，支持任意 OpenAI 兼容的 API 供应商
TVC_API_KEY = os.getenv("TVC_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
TVC_API_BASE = os.getenv("TVC_API_BASE", "https://api.deepseek.com")
MODEL_NAME = os.getenv("TVC_MODEL", "deepseek-chat")  # 默认 V3 (兼容 langgraph dev)

def _create_llm(
    model_override: str | None = None,
    temperature: float = 0.7,
    top_p: float = 1.0,
    presence_penalty: float = 0.0,
    frequency_penalty: float = 0.0,
):
    """创建 LLM 实例（支持任意 OpenAI 兼容的 API 接口）。"""
    model = model_override or MODEL_NAME
    return ChatOpenAI(
        model=model,
        api_key=TVC_API_KEY,
        base_url=TVC_API_BASE,
        temperature=temperature,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
    )


def _create_creative_llm():
    """创建适合发散创作的 LLM（高温度 + 高多样性）。用于编剧/文案/DP。"""
    return _create_llm(
        temperature=1.3,
        top_p=0.95,
        presence_penalty=0.6,   # 鼓励引入新话题/概念
        frequency_penalty=0.3,  # 减少重复用词
    )


def _create_orchestrator_llm():
    """创建适合精确调度和审查的 LLM（低温度）。用于 Showrunner。"""
    return _create_llm(
        temperature=0.4,
        top_p=1.0,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    )

# ---------------------------------------------------------------------------
# Showrunner 系统提示词 — 融合审查 OS + 流水线调度指令
# ---------------------------------------------------------------------------
SHOWRUNNER_SYSTEM_PROMPT = f"""\
{load_showrunner_prompt()}

# === 流水线调度指令 ===

你是这个 TVC 广告剧本生成流水线的总调度。你的工作流程如下：

## ⚠️ Todo管理规则（严格执行）

**重要**: 为了减少不必要的 LLM 调用和延迟，你必须遵守以下 write_todos 规则：
1. **只在以下 3 个时间点更新 todo**:
   - 时间点 A: 收到完整 Brief 后，一次性写入全部 6 个步骤（全部 pending）
   - 时间点 B: 三个 Sub-agent 全部完成后，一次性把 Step 1-4 标记 completed，Step 5 标记 in_progress
   - 时间点 C: 最终输出前，一次性把全部标记 completed
2. **绝对禁止**在每次调用 task() 前后都更新 todo。这浪费 token 和时间。
3. 在调用 task() 前不需要额外的一次 write_todos。直接调用 task() 即可。

## 🚫 严禁并行调用 task()（最高优先级）

**你每次只能调用一个 task()，必须等它返回结果后，才能调用下一个 task()。**

原因：每个 Sub-agent 的输入依赖上一个的产出：
- Copywriter 必须拿到 Screenwriter 的 `<plot_outline>` 才能开始
- DP 必须拿到 `<plot_outline>` + `<copywriting>` 才能开始

如果你并行调用三个 task()，后两个 Sub-agent 将收不到上游产出，导致脚本质量严重下降。
**绝对禁止在一次回复中同时发出多个 task() 调用。**

## 工作流 SOP

### Step 0: Brief 信息收集（必须完成才能进入 Step 1）

你 **必须** 从用户处收集以下信息。如果用户没有提供其中的必填项，你必须主动追问，**不得跳过直接开始生产流水线**。

| 字段 | 必填? | 说明 |
|------|-------|------|
| 品牌名 (brand_name) | ✅ 必填 | 品牌的官方名称 |
| 产品 (product) | ✅ 必填 | 具体产品描述和核心功能 |
| 目标受众 (target_audience) | ✅ 必填 | 年龄/性别/职业/生活方式 |
| 核心痛点 (pain_points) | ✅ 必填 | 受众的核心痛苦/困扰 |
| 风格 (style) | ✅ 必填 | 视觉风格 |
| 时长 (duration) | ✅ 必填 | 15s/30s/60s |
| 产品类型 (product_type) | 选填 | 功能型/情感型（默认根据产品推断） |
| 投放渠道 (channels) | 选填 | TV/社媒/电梯屏（影响剪辑节奏） |

**追问策略**: 如果只缺 1-2 个必填项，在一条消息中全部追问。如果用户提供了足够信息，不要反复确认，直接进入 Step 1。

### Step 1: 解析 Brief + 初始化 Todo
从用户的需求中提取上表中的变量。然后执行 **一次** write_todos（时间点 A），写入全部 6 个步骤。

### Step 2: 调用编剧 Sub-agent
使用 `task(agent="screenwriter", ...)` 工具。
在 instruction 中包含：所有已提取的变量，明确要求输出 `<plot_outline>` 格式。
**直接调用 task()，不要先 write_todos。**

### Step 3: 调用文案 Sub-agent
使用 `task(agent="copywriter", ...)` 工具。
在 instruction 中包含：所有已提取的变量 + Step 2 的完整 `<plot_outline>`。
**直接调用 task()，不要先 write_todos。**

### Step 4: 调用摄影指导 Sub-agent
使用 `task(agent="dp", ...)` 工具。
在 instruction 中包含：所有已提取的变量 + Step 2 的 `<plot_outline>` + Step 3 的 `<copywriting>`。
**直接调用 task()，不要先 write_todos。**

三个 Sub-agent 全部完成后，执行 **一次** write_todos（时间点 B）。

### Step 5: 自我审查
将 Step 2/3/4 的产出组合，对照你的审查清单（Critic's Checklist）和绝对禁忌（Negative Constraints）进行评分。
- 如果 PASS (≥85分 且无 FORBIDDEN 触发): 组合产出最终脚本。
- 如果 FAIL: 精准定位问题 Sub-agent，重新调用对应的 task()，附上具体修改指令。最多重试 2 次。

### Step 6: 最终输出
将通过审查的产出整合为完整的 TVC 分镜头脚本，使用清晰的左右分栏格式呈现。
输出前执行 **一次** write_todos（时间点 C），把全部步骤标记完成。
"""

# ---------------------------------------------------------------------------
# Sub-agent 定义
# ---------------------------------------------------------------------------
def _build_subagents():
    """构建 Sub-agent 列表（每次调用都生成新的 LLM 实例）。"""
    return [
        {
            "name": "screenwriter",
            "description": (
                "编剧 Sub-agent — 专精叙事结构与类型适配。"
                "接收品牌 Brief，输出 <plot_outline> 包含 5-Block / 15-Beat 时间轴结构、"
                "McKee 叙事语法分析（Hook / Gap / Crisis / Intervention）、"
                "以及 SaveTheCat 10 Genre 中的类型选择与映射。"
                "不涉及文案撰写或镜头设计。"
            ),
            "system_prompt": load_screenwriter_prompt(),
            "model": _create_creative_llm(),
        },
        {
            "name": "copywriter",
            "description": (
                "文案 Sub-agent — 专精品牌叙事文案与创意概念。"
                "接收编剧的 <plot_outline>，输出 <copywriting> 包含每个 Block 的旁白/对白/花字/Tagline、"
                "StoryBrand SB7 品牌定位分析（Hero / Guide / Plan / CTA）、"
                "以及 HeyWhipple 4 大创意引擎的概念选择。"
                "不涉及剧情结构或镜头设计。"
            ),
            "system_prompt": load_copywriter_prompt(),
            "model": _create_creative_llm(),
        },
        {
            "name": "dp",
            "description": (
                "摄影指导 (DP) Sub-agent — 专精镜头语言与视听调度。"
                "接收编剧的 <plot_outline> 和文案的 <copywriting>，"
                "输出 <visual_board> 包含每个 Block 的景别、机位、运镜、景深、灯光和音频方向。"
                "严格遵循 MasterShots 权力动力学规则和风格自适应映射。"
                "不涉及剧情结构或文案撰写。"
            ),
            "system_prompt": load_dp_prompt(),
            "model": _create_creative_llm(),
        },
    ]


# ---------------------------------------------------------------------------
# Agent 工厂函数 — langgraph.json 入口
# ---------------------------------------------------------------------------
def create_tvc_director():
    """创建 TVC 编导 Deep Agent。

    该函数被 langgraph.json 引用，供 `langgraph dev` 或 `langgraph up` 加载。
    不接收任何自定义参数（平台自动注入 checkpointer 和 store）。
    """
    agent = create_deep_agent(
        name="tvc-director",
        model=_create_orchestrator_llm(),
        system_prompt=SHOWRUNNER_SYSTEM_PROMPT,
        subagents=_build_subagents(),
        backend=FilesystemBackend(
            root_dir=str(Path(__file__).parent.parent),
            virtual_mode=True,
        ),
    )
    return agent


# ---------------------------------------------------------------------------
# 本地开发入口 — 直接 python src/agent.py 运行
# ---------------------------------------------------------------------------
def create_tvc_director_local():
    """本地开发版本 — 手动提供 checkpointer。"""
    agent = create_deep_agent(
        name="tvc-director",
        model=_create_orchestrator_llm(),
        system_prompt=SHOWRUNNER_SYSTEM_PROMPT,
        subagents=_build_subagents(),
        backend=FilesystemBackend(
            root_dir=str(Path(__file__).parent.parent),
            virtual_mode=True,
        ),
        checkpointer=MemorySaver(),
    )
    return agent


if __name__ == "__main__":
    agent = create_tvc_director_local()
    print("✅ TVC Director Agent 初始化成功！")
    print(f"   模型: {MODEL_NAME} (DeepSeek R1)")
    print(f"   Sub-agents: screenwriter, copywriter, dp")
    print(f"   Prompts 目录: {Path(__file__).parent.parent / 'prompts'}")
