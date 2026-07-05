from django.contrib import admin
from .models import Department, Subject, Class, TeacherSubjectClass, Assignment, Submission, Mark


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "hod")
    search_fields = ("name", "code")
    ordering = ("code",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department")
    list_filter = ("department",)
    search_fields = ("name", "code")
    ordering = ("department", "code")


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ("__str__", "department", "year", "section", "academic_year", "adviser")
    list_filter = ("department", "year", "academic_year")
    search_fields = ("department__name", "section")
    ordering = ("department", "year", "section")


@admin.register(TeacherSubjectClass)
class TeacherSubjectClassAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "student_class")
    list_filter = ("subject__department", "student_class__year")
    search_fields = ("teacher__user__username", "subject__name")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "student_class", "created_by", "due_date", "created_at")
    list_filter = ("subject__department", "student_class", "due_date")
    search_fields = ("title", "subject__name", "created_by__user__username")
    ordering = ("-created_at",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "submitted_at", "grade")
    list_filter = ("assignment__subject", "submitted_at")
    search_fields = ("student__regno", "student__name", "assignment__title")
    ordering = ("-submitted_at",)


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "exam_type", "marks_obtained", "max_marks", "date")
    list_filter = ("exam_type", "subject__department", "date")
    search_fields = ("student__regno", "student__name", "subject__name")
    ordering = ("-date",)
