from django.contrib import admin
from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "date", "status", "marked_by")
    list_filter = ("status", "date", "subject__department")
    search_fields = ("student__regno", "student__name", "subject__name")
    ordering = ("-date",)
