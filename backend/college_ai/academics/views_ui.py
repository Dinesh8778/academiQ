"""
Template-based UI views for CRUD management (admin) and attendance marking (teacher).
These are separate from the DRF viewsets in views.py.
"""
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages

from .models import Department, Subject, Class, Assignment, TeacherSubjectClass
from students.models import Student
from attendance.models import Attendance


def admin_required(view_func):
    """Decorator: user must be staff."""
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Admin access required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def teacher_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Teacher access required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---- Department CRUD ----

@method_decorator([login_required, admin_required], name='dispatch')
class DepartmentListView(View):
    def get(self, request):
        from users.models import Teacher
        return render(request, 'academics/department_list.html', {
            'departments': Department.objects.select_related('hod').all(),
            'teachers': Teacher.objects.select_related('user').all(),
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        hod_id = request.POST.get('hod', '') or None
        if not name or not code:
            messages.error(request, "Name and code are required.")
        elif Department.objects.filter(code=code).exists():
            messages.error(request, "Department code already exists.")
        else:
            Department.objects.create(name=name, code=code, hod_id=hod_id)
            messages.success(request, f"Department '{code}' created.")
        return redirect('department_list')


@method_decorator([login_required, admin_required], name='dispatch')
class DepartmentEditView(View):
    def get(self, request, pk):
        from users.models import Teacher
        dept = get_object_or_404(Department, pk=pk)
        return render(request, 'academics/department_form.html', {
            'dept': dept,
            'teachers': Teacher.objects.select_related('user').all(),
        })

    def post(self, request, pk):
        dept = get_object_or_404(Department, pk=pk)
        dept.name = request.POST.get('name', dept.name).strip()
        dept.code = request.POST.get('code', dept.code).strip()
        hod_id = request.POST.get('hod', '') or None
        dept.hod_id = hod_id
        dept.save()
        messages.success(request, "Department updated.")
        return redirect('department_list')


@method_decorator([login_required, admin_required], name='dispatch')
class DepartmentDeleteView(View):
    def post(self, request, pk):
        dept = get_object_or_404(Department, pk=pk)
        dept.delete()
        messages.success(request, "Department deleted.")
        return redirect('department_list')


# ---- Subject CRUD ----

@method_decorator([login_required, admin_required], name='dispatch')
class SubjectListView(View):
    def get(self, request):
        return render(request, 'academics/subject_list.html', {
            'subjects': Subject.objects.select_related('department').all(),
            'departments': Department.objects.all(),
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        dept_id = request.POST.get('department', '')
        if not name or not code or not dept_id:
            messages.error(request, "All fields required.")
        elif Subject.objects.filter(code=code).exists():
            messages.error(request, "Subject code already exists.")
        else:
            Subject.objects.create(name=name, code=code, department_id=dept_id)
            messages.success(request, f"Subject '{code}' created.")
        return redirect('subject_list')


@method_decorator([login_required, admin_required], name='dispatch')
class SubjectEditView(View):
    def get(self, request, pk):
        subj = get_object_or_404(Subject, pk=pk)
        return render(request, 'academics/subject_form.html', {
            'subj': subj, 'departments': Department.objects.all()})

    def post(self, request, pk):
        subj = get_object_or_404(Subject, pk=pk)
        subj.name = request.POST.get('name', subj.name).strip()
        subj.code = request.POST.get('code', subj.code).strip()
        dept_id = request.POST.get('department', '')
        if dept_id:
            subj.department_id = dept_id
        subj.save()
        messages.success(request, "Subject updated.")
        return redirect('subject_list')


@method_decorator([login_required, admin_required], name='dispatch')
class SubjectDeleteView(View):
    def post(self, request, pk):
        get_object_or_404(Subject, pk=pk).delete()
        messages.success(request, "Subject deleted.")
        return redirect('subject_list')


# ---- Class CRUD ----

@method_decorator([login_required, admin_required], name='dispatch')
class ClassListView(View):
    def get(self, request):
        return render(request, 'academics/class_list.html', {
            'classes': Class.objects.select_related('department', 'adviser__user').all(),
            'departments': Department.objects.all(),
        })

    def post(self, request):
        dept_id = request.POST.get('department', '')
        year = request.POST.get('year', '')
        section = request.POST.get('section', '').strip()
        academic_year = request.POST.get('academic_year', '2025-2026').strip()
        if not dept_id or not year or not section:
            messages.error(request, "Department, year, and section are required.")
        else:
            Class.objects.get_or_create(
                department_id=dept_id, year=year,
                section=section, academic_year=academic_year)
            messages.success(request, "Class created.")
        return redirect('class_list')


@method_decorator([login_required, admin_required], name='dispatch')
class ClassEditView(View):
    def get(self, request, pk):
        from users.models import Teacher
        cls = get_object_or_404(Class, pk=pk)
        return render(request, 'academics/class_form.html', {
            'cls': cls,
            'departments': Department.objects.all(),
            'teachers': Teacher.objects.select_related('user').all(),
        })

    def post(self, request, pk):
        cls = get_object_or_404(Class, pk=pk)
        cls.department_id = request.POST.get('department', cls.department_id)
        cls.year = request.POST.get('year', cls.year)
        cls.section = request.POST.get('section', cls.section).strip()
        cls.academic_year = request.POST.get('academic_year', cls.academic_year).strip()
        adviser_id = request.POST.get('adviser', '') or None
        cls.adviser_id = adviser_id
        cls.save()
        messages.success(request, "Class updated.")
        return redirect('class_list')


@method_decorator([login_required, admin_required], name='dispatch')
class ClassDeleteView(View):
    def post(self, request, pk):
        get_object_or_404(Class, pk=pk).delete()
        messages.success(request, "Class deleted.")
        return redirect('class_list')


# ---- Assignment create/list (teacher) ----

@method_decorator([login_required, teacher_required], name='dispatch')
class AssignmentCreateView(View):
    template_name = 'academics/assignment_form.html'

    def get(self, request):
        if request.user.is_staff:
            teaching = TeacherSubjectClass.objects.select_related(
                'subject', 'student_class').all()
        else:
            teaching = TeacherSubjectClass.objects.filter(
                teacher=request.user.teacher).select_related('subject', 'student_class')
        return render(request, self.template_name, {'teaching': teaching})

    def post(self, request):
        from django.utils import timezone
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date = request.POST.get('due_date', '')
        subject_id = request.POST.get('subject', '')
        class_id = request.POST.get('student_class', '')
        if not title or not due_date or not subject_id or not class_id:
            messages.error(request, "All fields required.")
            return redirect('assignment_create')
        teacher = request.user.teacher if hasattr(request.user, 'teacher') else None
        if teacher is None:
            messages.error(request, "Only teachers can create assignments.")
            return redirect('dashboard')
        a = Assignment.objects.create(
            title=title, description=description, due_date=due_date,
            subject_id=subject_id, student_class_id=class_id, created_by=teacher)
        messages.success(request, f"Assignment '{a.title}' created.")
        return redirect('teacher_dashboard')


# ---- Attendance marking (teacher) ----

@method_decorator([login_required, teacher_required], name='dispatch')
class AttendanceMarkView(View):
    template_name = 'academics/attendance_mark.html'

    def get(self, request):
        if request.user.is_staff:
            classes = Class.objects.select_related('department').all()
            subjects = Subject.objects.select_related('department').all()
        else:
            teacher = request.user.teacher
            tsc = TeacherSubjectClass.objects.filter(
                teacher=teacher).select_related('subject', 'student_class__department')
            classes = Class.objects.filter(
                teaching_assignments__teacher=teacher).distinct()
            subjects = Subject.objects.filter(
                teaching_assignments__teacher=teacher).distinct()
        students = []
        selected_class = request.GET.get('class_id', '')
        selected_subject = request.GET.get('subject_id', '')
        selected_date = request.GET.get('date', '')
        if selected_class:
            students = Student.objects.filter(
                student_class_id=selected_class, is_active=True).order_by('regno')
        return render(request, self.template_name, {
            'classes': classes, 'subjects': subjects,
            'students': students,
            'selected_class': selected_class,
            'selected_subject': selected_subject,
            'selected_date': selected_date,
        })

    def post(self, request):
        class_id = request.POST.get('class_id', '')
        subject_id = request.POST.get('subject_id', '')
        date = request.POST.get('date', '')
        teacher = getattr(request.user, 'teacher', None)
        students = Student.objects.filter(student_class_id=class_id, is_active=True)
        created, updated = 0, 0
        for student in students:
            status_val = request.POST.get(f'status_{student.pk}') == 'on'
            remarks = request.POST.get(f'remarks_{student.pk}', '').strip()
            _, was_created = Attendance.objects.update_or_create(
                student=student, subject_id=subject_id, date=date,
                defaults={'status': status_val, 'marked_by': teacher, 'remarks': remarks})
            if was_created:
                created += 1
            else:
                updated += 1
        messages.success(request, f"Attendance saved: {created} new, {updated} updated.")
        return redirect('teacher_dashboard')
