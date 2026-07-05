from django.db import models
from django.contrib.auth.models import User
from academics.models import Class


class Student(models.Model):

    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    # Link to Django auth (nullable — existing records won't break)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile"
    )

    # Core identity
    name = models.CharField(max_length=100)
    regno = models.CharField(max_length=12, unique=True)

    # Class assignment
    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="students"
    )

    # Extended profile fields
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    guardian_name = models.CharField(max_length=100, null=True, blank=True)
    date_enrolled = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["regno"]

    def __str__(self):
        return f"{self.regno} - {self.name}"
