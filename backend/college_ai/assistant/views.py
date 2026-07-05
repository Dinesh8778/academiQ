"""
assistant/views.py
==================
POST /api/assistant/ask/

Rate-limited to ASSISTANT_RATE_LIMIT (default 10/minute) per user.
Requires existing JWT or session authentication.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.utils.decorators import method_decorator
from django.conf import settings


@method_decorator(
    ratelimit(
        key='user',
        rate=getattr(settings, 'ASSISTANT_RATE_LIMIT', '10/m'),
        method='POST',
        block=True,
    ),
    name='dispatch',
)
class AssistantAskView(APIView):
    """
    POST /api/assistant/ask/

    Body: {"message": "...", "history": [...optional prior turns...]}

    Returns:
        {
            "answer": "...",
            "tools_called": [...],
            "role": "student|teacher|admin",
            "error": null
        }

    Rate limited: see settings.ASSISTANT_RATE_LIMIT
    Roles: any authenticated user (student/teacher/admin)
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Ask the AI assistant",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "User's question"},
                    "history": {
                        "type": "array",
                        "description": "Optional prior conversation turns",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string", "enum": ["user", "assistant"]},
                                "content": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["message"],
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "tools_called": {"type": "array", "items": {"type": "string"}},
                    "role": {"type": "string"},
                    "error": {"type": "string", "nullable": True},
                },
            },
            429: {"description": "Rate limit exceeded"},
        },
    )
    def post(self, request):
        message = request.data.get('message', '').strip()
        history = request.data.get('history', [])

        if not message:
            return Response(
                {"detail": "message field is required and cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(message) > 2000:
            return Response(
                {"detail": "Message too long. Maximum 2000 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from assistant.groq_client import call_groq
        from assistant.tools import get_user_role

        role = get_user_role(request.user)
        result = call_groq(request.user, message, conversation_history=history)

        return Response({
            "answer": result["answer"],
            "tools_called": result["tools_called"],
            "role": role,
            "error": result["error"],
            "draft_data": result.get("draft_data"),
        })

    def handle_exception(self, exc):
        if isinstance(exc, Ratelimited):
            return Response(
                {"detail": "Rate limit exceeded. Please wait before sending another message."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().handle_exception(exc)
