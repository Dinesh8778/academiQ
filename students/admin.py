from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("regno", "name", "student_class", "gender", "is_active", "date_enrolled")
    list_filter = ("is_active", "gender", "student_class__department")
    search_fields = ("regno", "name", "email")
    ordering = ("regno",)
    readonly_fields = ("date_enrolled",)
