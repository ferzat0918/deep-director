"""
测试脚本 — 发送一个 TVC Brief 给 Director Agent 并打印产出。

用法:
    python scripts/test_run.py
"""

import sys
import uuid
from pathlib import Path

# 确保能 import src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import create_tvc_director_local


def main():
    # --- 创建 Agent ---
    print("=" * 60)
    print("🎬 TVC 编导 Deep Agent — 测试运行")
    print("=" * 60)

    agent = create_tvc_director_local()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    # --- 测试 Brief ---
    test_brief = """
    请帮我生成一个 TVC 广告脚本：

    品牌/产品：某降噪耳机品牌
    目标受众：一线城市 25-35 岁的职场通勤白领
    核心痛点：每天地铁通勤噪音轰炸，无法在碎片时间获得内心平静
    风格：惊悚/紧张 转 温馨/治愈
    时长：60 秒
    产品类型：功能型
    """

    print(f"\n📋 测试 Brief:\n{test_brief}")
    print("=" * 60)
    print("🚀 开始运行 Agent...\n")

    # --- 运行 Agent (流式输出) ---
    for event in agent.stream(
        {"messages": [{"role": "user", "content": test_brief}]},
        config=config,
        stream_mode="updates",
    ):
        # 打印每个节点的更新
        for node_name, update in event.items():
            if node_name == "__interrupt__":
                print(f"\n⏸️  Agent 暂停，等待审批...")
                continue
            print(f"\n--- [{node_name}] ---")

            # Deep Agent 用 Overwrite 包装 state 字段，需要解包
            if isinstance(update, dict):
                for key, value in update.items():
                    # 解包 Overwrite 对象
                    actual_value = value
                    if hasattr(value, "value"):
                        actual_value = value.value

                    if key == "messages" and isinstance(actual_value, list):
                        for msg in actual_value:
                            if hasattr(msg, "content") and msg.content:
                                content = msg.content
                                if len(content) > 800:
                                    print(content[:800] + "\n... [截断]")
                                else:
                                    print(content)
                    elif key == "todos" and isinstance(actual_value, list):
                        for todo in actual_value:
                            status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(
                                todo.get("status", ""), "❓"
                            )
                            print(f"  {status_icon} {todo.get('content', '???')}")
            else:
                print(f"  {update}")

    # --- 获取最终状态 ---
    final_state = agent.get_state(config)
    print("\n" + "=" * 60)
    print("✅ 运行完成！")

    # 打印 TodoList 状态
    todos = final_state.values.get("todos", [])
    if todos:
        print("\n📋 TodoList 最终状态:")
        for todo in todos:
            status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(
                todo.get("status", ""), "❓"
            )
            print(f"  {status_icon} {todo.get('content', '???')}")

    print("=" * 60)


if __name__ == "__main__":
    main()
