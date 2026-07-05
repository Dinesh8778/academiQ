from django.db import models
from django.contrib.auth.models import User



class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    teacher_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey("academics.Department", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['teacher_id']

    def __str__(self):
        return f"{self.user.username} ({self.teacher_id})"


class CredentialChangeLog(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credential_changes_made')
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credential_changes_received')
    action_type = models.CharField(max_length=50)  # "username", "password", or "both"
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Change by {self.admin.username} on {self.target_user.username} - {self.action_type} at {self.timestamp}"