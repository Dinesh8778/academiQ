"""
ai_engine/views.py
==================
DRF API views for the AI risk scoring endpoint.

Endpoints:
  GET /api/ai/risk-scores/                 all students
  GET /api/ai/risk-scores/<class_id>/      filtered by class

Access: Teacher and Admin only. Students are explicitly denied.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter

from users.permissions import IsAdminOrTeacher


class RiskScoreView(APIView):
    """
    Returns predicted risk scores for all active students.
    Restricted to Teacher and Admin roles only.
    """
    permission_classes = [IsAdminOrTeacher]

    @extend_schema(
        summary="Get AI risk scores for all students",
        description=(
            "Returns the model-predicted risk label and probability score "
            "for every active student. Labels are derived from a rule-based "
            "ground truth (attendance < 75% OR marks < 40% OR missed submissions > 30%). "
            "This is a demonstration model trained on rule-derived labels, "
            "NOT real historical outcome data."
        ),
        responses={
            200: {
                "type": "object",
                "properties": {
                    "model_available": {"type": "boolean"},
                    "total_students": {"type": "integer"},
                    "at_risk_count": {"type": "integer"},
                    "results": {"type": "array"},
                },
            }
        },
    )
    def get(self, request, class_id=None):
        from ai_engine.predictor import predict_risk

        try:
            results = predict_risk(class_id=class_id)
        except FileNotFoundError as e:
            return Response(
                {
                    "model_available": False,
                    "detail": str(e),
                    "hint": "Run: python manage.py seed_ai_data && python manage.py train_risk_model",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            return Response(
                {"detail": f"Prediction error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        at_risk_count = sum(1 for r in results if r['at_risk_label'] == 1)

        return Response({
            "model_available": True,
            "total_students": len(results),
            "at_risk_count": at_risk_count,
            "class_id": class_id,
            "disclaimer": (
                "Labels are rule-derived, not from real historical outcomes. "
                "Do not use for production academic decisions without expert validation."
            ),
            "results": results,
        })
