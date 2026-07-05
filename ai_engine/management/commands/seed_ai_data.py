"""
Management command: seed_ai_data

Creates synthetic but realistic student data for AI model training.
Generates 30 students across 3 risk profiles:
  - 10 clearly at-risk   (low attendance, low marks, missed submissions)
  - 10 clearly safe      (high attendance, high marks, few missed submissions)
  - 10 borderline        (mixed signals near thresholds)

All data is generated deterministically (seed=42) so re-runs are idempotent.
⚠️  This is synthetic data for demonstration. Do not use for production decisions.

Usage:
    python manage.py seed_ai_data
    python manage.py seed_ai_data --class_id 1  (attach to existing class)
"""

import random
from datetime import date, timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from academics.models import Department, Class, Subject, Assignment, TeacherSubjectClass
from students.models import Student
from attendance.models import Attendance
from academics.models import Mark, Submission
from users.models import Teacher


class Command(BaseCommand):
    help = "Seed synthetic student data for AI model training."

    def add_arguments(self, parser):
        parser.add_argument('--class_id', type=int, default=None,
                            help="Attach seeded students to this class ID.")

    def handle(self, *args, **options):
        rng = random.Random(42)
        self.stdout.write("--- Seeding AI training data ---")

        # ---- Ensure a department, class, and subject exist ----
        dept, _ = Department.objects.get_or_create(
            code='SEED', defaults={'name': 'Seed Department'}
        )
        cls_id = options.get('class_id')
        if cls_id:
            try:
                cls = Class.objects.get(pk=cls_id)
            except Class.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Class {cls_id} not found."))
                return
        else:
            cls, _ = Class.objects.get_or_create(
                department=dept, year=2, section='SEED', academic_year='2025-2026'
            )

        subj, _ = Subject.objects.get_or_create(
            code='SEED101', defaults={'name': 'Seed Subject', 'department': dept}
        )

        # ---- Ensure a teacher exists for marking attendance ----
        seed_teacher_user, created = User.objects.get_or_create(
            username='seed_teacher',
            defaults={'email': 'seed@college.edu', 'first_name': 'Seed', 'last_name': 'Teacher'}
        )
        if created:
            seed_teacher_user.set_password('Seed@1234')
            seed_teacher_user.save()
        teacher, _ = Teacher.objects.get_or_create(
            user=seed_teacher_user,
            defaults={'teacher_id': 'SEED_T01', 'department': dept}
        )
        TeacherSubjectClass.objects.get_or_create(
            teacher=teacher, subject=subj, student_class=cls
        )

        # ---- Create 3 assignments ----
        assignments = []
        for i in range(1, 4):
            a, _ = Assignment.objects.get_or_create(
                title=f'Seed Assignment {i}',
                defaults={
                    'description': f'Auto-generated assignment {i}',
                    'due_date': timezone.make_aware(
                        timezone.datetime(2025, 9, i * 10)
                    ),
                    'subject': subj,
                    'student_class': cls,
                    'created_by': teacher,
                }
            )
            assignments.append(a)

        # ---- Define 3 profile types ----
        profiles = {
            'at_risk':    {'att': (40, 70),  'marks': (20, 39), 'submit': (0, 1)},
            'safe':       {'att': (80, 100), 'marks': (60, 95), 'submit': (2, 3)},
            'borderline': {'att': (68, 80),  'marks': (38, 55), 'submit': (1, 2)},
        }

        created_count = 0
        today = date(2026, 1, 1)  # fixed reference point for reproducibility

        for profile_name, profile_cfg in profiles.items():
            for i in range(1, 11):
                regno = f'SEED{profile_name[:2].upper()}{i:03d}'
                username = f'seed_{profile_name[:2]}_{i}'

                if Student.objects.filter(regno=regno).exists():
                    continue

                u = User.objects.create_user(
                    username=username, password='Seed@1234',
                    email=f'{username}@seed.edu'
                )
                student = Student.objects.create(
                    user=u, name=f'Seed {profile_name.title()} {i}',
                    regno=regno, student_class=cls, is_active=True
                )

                # Attendance: 60 days back
                att_min, att_max = profile_cfg['att']
                att_pct = rng.uniform(att_min, att_max) / 100
                for d in range(60):
                    day = today - timedelta(days=60 - d)
                    Attendance.objects.create(
                        student=student, subject=subj, date=day,
                        status=rng.random() < att_pct,
                        marked_by=teacher,
                    )

                # Marks: 2 exams
                mark_min, mark_max = profile_cfg['marks']
                exam_types = ['UT1', 'MID']
                for idx, etype in enumerate(exam_types):
                    score = rng.uniform(mark_min, mark_max)
                    # add slight trend variation
                    if profile_name == 'at_risk':
                        score = max(0, score - idx * 3)  # declining
                    elif profile_name == 'safe':
                        score = min(100, score + idx * 2)  # improving
                    Mark.objects.create(
                        student=student, subject=subj, exam_type=etype,
                        marks_obtained=round(score, 1), max_marks=100,
                        date=date(2025, 9 + idx, 15)
                    )

                # Submissions
                submit_min, submit_max = profile_cfg['submit']
                n_submitted = rng.randint(submit_min, submit_max)
                for a in assignments[:n_submitted]:
                    Submission.objects.get_or_create(
                        assignment=a, student=student,
                        defaults={'file': 'submissions/seed/placeholder.txt'}
                    )

                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Created {created_count} seeded students in class '{cls}'."
        ))
        self.stdout.write(f"  Department: {dept.code}, Subject: {subj.code}")
        self.stdout.write(
            "  Now run: python manage.py train_risk_model"
        )
