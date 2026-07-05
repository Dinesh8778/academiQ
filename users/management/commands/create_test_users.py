"""
Management command: create_test_users

Creates one admin, one teacher, and one student for manual testing.
Safe to run multiple times — skips creation if username already exists.

Usage:
    python manage.py create_test_users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from academics.models import Department, Class
from users.models import Teacher
from students.models import Student


class Command(BaseCommand):
    help = "Create test admin, teacher, and student accounts."

    def handle(self, *args, **options):
        self.stdout.write("--- Creating test users ---")

        # ---------------------------------------------------------------
        # 1. Admin
        # ---------------------------------------------------------------
        if User.objects.filter(username='admin_test').exists():
            self.stdout.write(self.style.WARNING("  [SKIP] admin_test already exists"))
        else:
            User.objects.create_superuser(
                username='admin_test',
                password='Admin@1234',
                email='admin@college.edu',
            )
            self.stdout.write(self.style.SUCCESS("  [OK] admin_test created (password: Admin@1234)"))

        # ---------------------------------------------------------------
        # 2. Department (required by Teacher and Class)
        # ---------------------------------------------------------------
        dept, dept_created = Department.objects.get_or_create(
            code='CSE',
            defaults={'name': 'Computer Science & Engineering'},
        )
        if dept_created:
            self.stdout.write(self.style.SUCCESS("  [OK] Department CSE created"))
        else:
            self.stdout.write(self.style.WARNING("  [SKIP] Department CSE already exists"))

        # ---------------------------------------------------------------
        # 3. Teacher
        # ---------------------------------------------------------------
        if User.objects.filter(username='teacher_test').exists():
            self.stdout.write(self.style.WARNING("  [SKIP] teacher_test already exists"))
        else:
            teacher_user = User.objects.create_user(
                username='teacher_test',
                password='Teacher@1234',
                email='teacher@college.edu',
                first_name='Jane',
                last_name='Smith',
            )
            Teacher.objects.create(
                user=teacher_user,
                teacher_id='TCH001',
                department=dept,
            )
            self.stdout.write(self.style.SUCCESS("  [OK] teacher_test created (password: Teacher@1234)"))

        # ---------------------------------------------------------------
        # 4. Class (required by Student)
        # ---------------------------------------------------------------
        cls, cls_created = Class.objects.get_or_create(
            department=dept,
            year=1,
            section='A',
            academic_year='2025-2026',
        )
        if cls_created:
            self.stdout.write(self.style.SUCCESS("  [OK] Class CSE Year 1 A (2025-2026) created"))
        else:
            self.stdout.write(self.style.WARNING("  [SKIP] Class already exists"))

        # ---------------------------------------------------------------
        # 5. Student
        # ---------------------------------------------------------------
        if User.objects.filter(username='student_test').exists():
            self.stdout.write(self.style.WARNING("  [SKIP] student_test already exists"))
        else:
            student_user = User.objects.create_user(
                username='student_test',
                password='Student@1234',
                email='student@college.edu',
                first_name='John',
                last_name='Doe',
            )
            Student.objects.create(
                user=student_user,
                name='John Doe',
                regno='CSE2025001',
                student_class=cls,
                email='student@college.edu',
            )
            self.stdout.write(self.style.SUCCESS("  [OK] student_test created (password: Student@1234)"))

        self.stdout.write("\n--- Summary ---")
        self.stdout.write("  admin_test   / Admin@1234   → /auth/dashboard/admin/")
        self.stdout.write("  teacher_test / Teacher@1234 → /auth/dashboard/teacher/")
        self.stdout.write("  student_test / Student@1234 → /auth/dashboard/student/")
        self.stdout.write("\nTest API auth:")
        self.stdout.write("  POST /api/auth/token/ with {username, password}")
        self.stdout.write("  GET  /api/auth/me/   with Authorization: Bearer <token>")
