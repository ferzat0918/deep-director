"""
Prompt Loader — 从 prompts/ 目录加载所有 OS Markdown 文件。
每个 Sub-agent 的 system_prompt 由一个或多个 OS 文件拼接而成。
"""

import os
from pathlib import Path

# prompts/ 目录位于项目根
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """加载单个 prompt 文件的内容。"""
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Prompt file not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


def load_screenwriter_prompt() -> str:
    """编剧 Agent 的 system_prompt。
    合并: Universal (叙事原则) + SaveTheCat (结构执行) + Genre Library (类型参考)
    """
    parts = [
        "# === 叙事原则层 (McKee) ===\n",
        _load_prompt("Universal_TVC_Director_OS.md"),
        "\n\n# === 结构执行层 (SaveTheCat 15-Beat) ===\n",
        _load_prompt("SaveTheCat_Master_TVC_Director_OS.md"),
        "\n\n# === 类型适配库 (10 Genre Adapters — 参考) ===\n",
        _load_prompt("SaveTheCat_Genre_Library.md"),
    ]
    return "\n".join(parts)


def load_copywriter_prompt() -> str:
    """文案 Agent 的 system_prompt。
    合并: StoryBrand (品牌叙事 SB7) + HeyWhipple (创意引擎)
    """
    parts = [
        "# === 品牌叙事层 (StoryBrand SB7) ===\n",
        _load_prompt("StoryBrand_Master_TVC_Director_OS.md"),
        "\n\n# === 创意引擎层 (HeyWhipple) ===\n",
        _load_prompt("HeyWhipple_Master_TVC_Director_OS.md"),
    ]
    return "\n".join(parts)


def load_dp_prompt() -> str:
    """摄影指导 Agent 的 system_prompt。
    单独: MasterShots (镜头权力动力学 + 风格映射)
    """
    return _load_prompt("MasterShots_Camera_Director_OS.md")


def load_showrunner_prompt() -> str:
    """监制 Agent (主 Agent) 的 system_prompt。
    Showrunner Critic OS (审查清单 + 绝对禁忌 + 跨Agent一致性)
    """
    return _load_prompt("Showrunner_Critic_OS.md")
