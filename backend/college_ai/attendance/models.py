from django.db import models
from students.models import Student
from academics.models import Subject


class Attendance(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )
    date = models.DateField()
    status = models.BooleanField()  # True = Present, False = Absent

    # New fields
    marked_by = models.ForeignKey(
        "users.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendances"
    )
    remarks = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ("student", "subject", "date")
        ordering = ["-date"]

    def __str__(self):
        status_label = "Present" if self.status else "Absent"
        return f"{self.student} | {self.subject} | {self.date} | {status_label}"
