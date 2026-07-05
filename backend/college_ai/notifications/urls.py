from django.urls import path
from .views import MarkNotificationReadView

urlpatterns = [
    path('<int:pk>/mark-read/', MarkNotificationReadView.as_view(), name='mark_notification_read'),
]
