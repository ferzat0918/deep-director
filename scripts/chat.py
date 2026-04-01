"""
交互式终端聊天脚本 — 通过命令行直接与 TVC Director Agent 对话。
终端模式下默认使用 DeepSeek R1 (deepseek-reasoner)，追求最高质量。

用法:
    python scripts/chat.py
"""

import os
import sys
import uuid
from pathlib import Path

# 确保能 import src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# 终端模式默认使用 R1 (质量最高)，但优先尊重 .env 中的设置
if "TVC_MODEL" not in os.environ:
    os.environ["TVC_MODEL"] = "deepseek-reasoner"

from src.agent import create_tvc_director_local
from langgraph.types import Command

def print_separator():
    print("\n" + "=" * 60 + "\n")

def main():
    print_separator()
    print("🎬 欢迎使用 TVC 编导 Deep Agent 交互终端")
    print("💡 提示：输入 'quit' 或 'exit' 退出聊天")
    print("💡 提示：输入 '///' 可开始多行输入，完成后按 Ctrl+D (Mac/Linux) / Ctrl+Z (Windows) 提交")
    print_separator()

    # 初始化本地 Agent
    try:
        agent = create_tvc_director_local()
    except Exception as e:
        print(f"❌ Agent 初始化失败: {e}")
        return

    # 生成唯一的 thread_id 以保持当前会话记忆
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"✅ Agent 初始化成功！[Session ID: {thread_id[:8]}]")
    print("请描述你想拍摄的 TVC 广告（如：品牌、目标人群、痛点、风格等）...\n")

    while True:
        try:
            user_input = input("👤 You: ").strip()
            
            # 支持多行输入
            if user_input == "///":
                print("(进入多行输入模式，输入完毕请按 Ctrl+Z 然后回车提交)...")
                user_input = sys.stdin.read().strip()
                print("--- 提交成功 ---")
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit"]:
                print("\n👋 感谢使用，再见！")
                break

            print("\n🤖 TVC Director (Thinking & Delegating...)")
            print("-" * 40)

            # --- 运行 Agent 并流式输出 ---
            for event in agent.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, update in event.items():
                    if node_name == "__interrupt__":
                        print(f"\n⏸️ Agent 暂停执行，等待人工确认或修改任务...")
                        # 简单的自动恢复机制（如果有打断的话）
                        continue
                        
                    # 打印正在调用的 Sub-agent 工具
                    if node_name == "tools":
                        print(f"  [🛠️ Tools Executed]")
                        continue
                        
                    # 尝试非阻塞地剥离 Overwrite 包装
                    if isinstance(update, dict):
                        for key, value in update.items():
                            actual_value = value
                            if hasattr(value, "value"):
                                actual_value = value.value
                                
                            if key == "messages" and isinstance(actual_value, list):
                                for msg in actual_value:
                                    if hasattr(msg, "content") and msg.content:
                                        print(f"\n[{node_name}] -> {msg.content}")
                            elif key == "todos" and isinstance(actual_value, list):
                                # TodoList 状态更新，不在主聊天流强烈显示，只简单标记
                                pass

            # 打印当前 TodoList 的简要状态
            final_state = agent.get_state(config)
            todos = final_state.values.get("todos", [])
            pending_todos = [t for t in todos if t.get("status") in ("pending", "in_progress")]
            if pending_todos:
                print(f"\n📋 当前剩余 {len(pending_todos)} 个待办任务未完成...")
            else:
                print(f"\n✅ 所有待办任务已完成。")

            print_separator()

        except KeyboardInterrupt:
            print("\n👋 感谢使用，再见！")
            break
        except Exception as e:
            print(f"\n❌ 运行发生错误: {e}")
            print_separator()

if __name__ == "__main__":
    main()
