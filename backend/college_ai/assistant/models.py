from django.db import models
from django.contrib.auth.models import User

class DraftActionLog(models.Model):
    ACTION_CHOICES = [
        ('low_attendance_notice', 'Low Attendance Notice'),
        ('weekly_summary_report', 'Weekly Summary Report'),
    ]
    STATUS_CHOICES = [
        ('drafted', 'Drafted'),
        ('confirmed', 'Confirmed'),
        ('discarded', 'Discarded'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='draft_actions')
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    details = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='drafted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __font__(self):
        return f"{self.user.username} - {self.action_type} ({self.status}) at {self.created_at}"

