from django.urls import path
from .views import RiskScoreView

urlpatterns = [
    path('risk-scores/',               RiskScoreView.as_view(), name='ai_risk_scores'),
    path('risk-scores/<int:class_id>/', RiskScoreView.as_view(), name='ai_risk_scores_class'),
]
