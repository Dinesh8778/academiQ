from django.db import models
from django.contrib.auth.models import User



class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    teacher_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey("academics.Department", on_delete=models.CASCADE)

    class Meta:
        ordering = ['teacher_id']

    def __str__(self):
        return f"{self.user.username} ({self.teacher_id})"