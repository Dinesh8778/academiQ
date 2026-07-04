from django.db import models


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, default="", help_text="Short identifier, e.g. CSE, IT, ECE")

    hod = models.ForeignKey(
        "users.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments"
    )

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------
class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="subjects"
    )

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------
class Class(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="classes"
    )

    year = models.IntegerField()
    section = models.CharField(max_length=5)
    academic_year = models.CharField(
        max_length=9,
        help_text="Format: YYYY-YYYY, e.g. 2025-2026",
        default="2025-2026"
    )

    adviser = models.ForeignKey(
        "users.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advised_classes"
    )

    class Meta:
        unique_together = ("department", "year", "section", "academic_year")
        verbose_name = "Class"
        verbose_name_plural = "Classes"

    def __str__(self):
        return f"{self.department.code} Year {self.year} {self.section} ({self.academic_year})"


# ---------------------------------------------------------------------------
# TeacherSubjectClass  — who teaches what subject to which class
# ---------------------------------------------------------------------------
class TeacherSubjectClass(models.Model):
    teacher = models.ForeignKey(
        "users.Teacher",
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )
    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )

    class Meta:
        unique_together = ("teacher", "subject", "student_class")
        verbose_name = "Teacher Subject Class"
        verbose_name_plural = "Teacher Subject Classes"

    def __str__(self):
        return f"{self.teacher} → {self.subject} → {self.student_class}"


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
class Assignment(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField()

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    created_by = models.ForeignKey(
        "users.Teacher",
        on_delete=models.CASCADE,
        related_name="created_assignments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} | {self.subject} | {self.student_class}"


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
class Submission(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions"
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="submissions"
    )

    file = models.FileField(
        upload_to="submissions/%Y/%m/%d/",
        null=True,
        blank=True
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Grading (filled by teacher after review)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ("assignment", "student")
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.student} → {self.assignment}"


# ---------------------------------------------------------------------------
# Mark / Grade
# ---------------------------------------------------------------------------
class Mark(models.Model):

    EXAM_TYPE_CHOICES = [
        ("UT1", "Unit Test 1"),
        ("UT2", "Unit Test 2"),
        ("MID", "Mid Semester"),
        ("END", "End Semester"),
        ("INT", "Internal"),
        ("PRJ", "Project"),
        ("LAB", "Lab Exam"),
        ("OTH", "Other"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="marks"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="marks"
    )
    exam_type = models.CharField(max_length=3, choices=EXAM_TYPE_CHOICES)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    max_marks = models.DecimalField(max_digits=5, decimal_places=2)
    date = models.DateField()

    class Meta:
        unique_together = ("student", "subject", "exam_type")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} | {self.subject} | {self.exam_type} | {self.marks_obtained}/{self.max_marks}"

    @property
    def percentage(self):
        if self.max_marks > 0:
            return round((self.marks_obtained / self.max_marks) * 100, 2)
        return 0
