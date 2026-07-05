"""
assistant/groq_client.py
========================
Thin wrapper around the Groq API (OpenAI-compatible).

Groq's API is fully OpenAI-compatible, so we use the `openai` Python package
pointed at Groq's base URL. The API key is read from settings — never hardcoded.

Model used: llama-3.3-70b-versatile (fast, supports tool/function calling)

FLOW:
  1. Build initial message list with system prompt + user message
  2. Call Groq with tool definitions for the user's role
  3. If Groq returns tool_calls: execute each tool server-side via dispatch_tool_call
  4. Append tool results to messages and call Groq again for final answer
  5. Return the final natural-language response

The LLM NEVER sees raw querysets — it only receives serialised JSON dicts
returned by the tool functions.
"""

from __future__ import annotations
import json
from typing import Optional


def _get_client():
    """Create and return an OpenAI client pointed at the Groq API endpoint."""
    from django.conf import settings
    from openai import OpenAI

    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set in .env. "
            "Add GROQ_API_KEY=your-key to .env"
        )
    return OpenAI(
        api_key=api_key,
        base_url=settings.GROQ_API_BASE_URL,
    )


def get_system_prompt(role: str) -> str:
    """Role-specific system prompt."""
    base = (
        "You are AcademiQ Assistant, a helpful AI for an academic management system. "
        "You have access to tools that query real academic data. "
        "Always use tools to fetch live data before answering data-related questions. "
        "Be concise, accurate, and professional. "
        "If a tool returns an ACCESS_DENIED error, politely explain the user cannot access that data. "
        "Never fabricate data — only report what the tools return."
    )
    role_extras = {
        'student': " You are speaking with a student. Only use student-scoped tools.",
        'teacher': " You are speaking with a teacher. Only use teacher-scoped tools.",
        'admin':   " You are speaking with an administrator. You have access to system-wide tools.",
        'unknown': " You have limited access. Direct the user to contact an administrator.",
    }
    return base + role_extras.get(role, '')


def call_groq(user, message: str, conversation_history: Optional[list] = None) -> dict:
    """
    Main entry point. Handles the full tool-calling loop with Groq.

    Parameters
    ----------
    user        : Django auth User instance
    message     : The user's current message
    conversation_history : Optional list of prior {role, content} dicts

    Returns
    -------
    dict with keys:
        answer       : str  — the final natural-language response
        tools_called : list of tool names that were invoked
        error        : str or None
    """
    from assistant.tools import get_user_role, get_tools_for_role, dispatch_tool_call
    from django.conf import settings

    role = get_user_role(user)
    tools = get_tools_for_role(role)

    # Intercept write/create/delete/update requests immediately
    message_lower = message.lower()
    write_keywords = ["add", "create", "delete", "remove", "update", "edit", "insert", "modify", "register"]
    import re
    has_write_intent = any(re.search(r'\b' + re.escape(kw) + r'\b', message_lower) for kw in write_keywords)
    if has_write_intent and "draft" not in message_lower:
        element = "Teacher"
        if "student" in message_lower:
            element = "Student"
        elif "class" in message_lower:
            element = "Class"
        elif "department" in message_lower:
            element = "Department"
        elif "subject" in message_lower:
            element = "Subject"
        return {
            "answer": f"I can't create or edit records — I can only answer questions about existing students, teachers, attendance, and grades. Try the 'Add {element}' button on your dashboard instead.",
            "tools_called": [],
            "error": None,
        }

    messages = [{"role": "system", "content": get_system_prompt(role)}]
    if conversation_history:
        messages.extend(conversation_history[-6:])  # keep last 3 exchanges
    messages.append({"role": "user", "content": message})

    # Graceful offline response if key not configured
    if not settings.GROQ_API_KEY:
        return {
            "answer": (
                "The AI assistant is not configured yet. "
                "Please add GROQ_API_KEY to the .env file to enable the assistant."
            ),
            "tools_called": [],
            "error": "GROQ_API_KEY_MISSING",
        }

    try:
        client = _get_client()
        model = settings.GROQ_MODEL
        tools_called = []
        draft_data = None

        # ------------------------------------------------------------------
        # Round 1: Send message + tool definitions to Groq
        # ------------------------------------------------------------------
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.3,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        response_message = response.choices[0].message

        # ------------------------------------------------------------------
        # Round 2: Execute tool calls if Groq requested any
        # ------------------------------------------------------------------
        if response_message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response_message.tool_calls
                ],
            })

            for tool_call in response_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = dispatch_tool_call(user, fn_name, fn_args)
                tools_called.append(fn_name)

                # Capture draft details if a tool proposes a write
                if isinstance(tool_result, dict) and tool_result.get("action") == "propose_draft":
                    draft_data = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result),
                })

            # Round 2: Send tool results back to Groq for final answer
            final_response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
            )
            answer = final_response.choices[0].message.content or ""

        else:
            # No tool calls — direct conversational answer
            answer = response_message.content or "I couldn't generate a response."

        return {
            "answer": answer,
            "tools_called": tools_called,
            "draft_data": draft_data,
            "error": None,
        }

    except Exception as e:
        return {
            "answer": "I encountered an error processing your request. Please try again.",
            "tools_called": [],
            "draft_data": None,
            "error": str(e),
        }
