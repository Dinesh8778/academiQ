"""
Template-based UI views for CRUD management (admin) and attendance marking (teacher).
These are separate from the DRF viewsets in views.py.
"""
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages

from .models import Department, Subject, Class, Assignment, TeacherSubjectClass, Mark
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


@method_decorator([login_required, admin_required], name='dispatch')
class TeacherSubjectClassListView(View):
    template_name = 'academics/teacher_subject_class_list.html'

    def get(self, request):
        from users.models import Teacher
        assignments = TeacherSubjectClass.objects.select_related('teacher__user', 'subject', 'student_class').all()
        teachers = Teacher.objects.select_related('user').all()
        subjects = Subject.objects.select_related('department').all()
        classes = Class.objects.select_related('department').all()
        return render(request, self.template_name, {
            'assignments': assignments,
            'teachers': teachers,
            'subjects': subjects,
            'classes': classes,
        })

    def post(self, request):
        from users.models import Teacher
        teacher_id = request.POST.get('teacher', '')
        subject_id = request.POST.get('subject', '')
        class_id = request.POST.get('student_class', '')

        if not teacher_id or not subject_id or not class_id:
            messages.error(request, "All fields are required.")
        else:
            obj, created = TeacherSubjectClass.objects.get_or_create(
                teacher_id=teacher_id,
                subject_id=subject_id,
                student_class_id=class_id,
            )
            if created:
                messages.success(request, "Assigned teacher to subject successfully.")
            else:
                messages.warning(request, "This assignment already exists.")
        return redirect('teacher_subject_class_list')


@method_decorator([login_required, admin_required], name='dispatch')
class TeacherSubjectClassDeleteView(View):
    def post(self, request, pk):
        assignment = get_object_or_404(TeacherSubjectClass, pk=pk)
        assignment.delete()
        messages.success(request, "Teacher assignment removed.")
        return redirect('teacher_subject_class_list')


# ---- General Assignment Management (Admin/Teacher) ----

@method_decorator([login_required], name='dispatch')
class AssignmentListView(View):
    template_name = 'academics/assignment_list.html'

    def get(self, request):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        if request.user.is_staff:
            assignments = Assignment.objects.select_related('subject', 'student_class', 'created_by__user').all()
        else:
            teacher = request.user.teacher
            assignments = Assignment.objects.filter(created_by=teacher).select_related('subject', 'student_class', 'created_by__user').all()

        from django.db.models import Count
        assignments = assignments.annotate(submission_count=Count('submissions'))

        return render(request, self.template_name, {
            'assignments': assignments,
        })


@method_decorator([login_required], name='dispatch')
class AssignmentEditView(View):
    template_name = 'academics/assignment_edit_form.html'

    def get(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        assignment = get_object_or_404(Assignment, pk=pk)

        if not request.user.is_staff and assignment.created_by != request.user.teacher:
            messages.error(request, "Access denied.")
            return redirect('assignment_list')

        if request.user.is_staff:
            subjects = Subject.objects.select_related('department').all()
            classes = Class.objects.select_related('department').all()
        else:
            teacher = request.user.teacher
            from academics.models import TeacherSubjectClass
            teaching = TeacherSubjectClass.objects.filter(teacher=teacher).select_related('subject', 'student_class')
            subjects = {t.subject for t in teaching}
            classes = {t.student_class for t in teaching}

        subjects = sorted(list(subjects), key=lambda x: x.name)
        classes = sorted(list(classes), key=lambda x: str(x))

        return render(request, self.template_name, {
            'assignment': assignment,
            'subjects': subjects,
            'classes': classes,
            'action': 'Edit',
            'form_data': {}
        })

    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        assignment = get_object_or_404(Assignment, pk=pk)

        if not request.user.is_staff and assignment.created_by != request.user.teacher:
            messages.error(request, "Access denied.")
            return redirect('assignment_list')

        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date = request.POST.get('due_date', '')
        subject_id = request.POST.get('subject', '')
        class_id = request.POST.get('student_class', '')

        if not title or not due_date or not subject_id or not class_id:
            messages.error(request, "Title, due date, subject, and class are required.")
            if request.user.is_staff:
                subjects = Subject.objects.select_related('department').all()
                classes = Class.objects.select_related('department').all()
            else:
                teacher = request.user.teacher
                from academics.models import TeacherSubjectClass
                teaching = TeacherSubjectClass.objects.filter(teacher=teacher).select_related('subject', 'student_class')
                subjects = {t.subject for t in teaching}
                classes = {t.student_class for t in teaching}
            subjects = sorted(list(subjects), key=lambda x: x.name)
            classes = sorted(list(classes), key=lambda x: str(x))

            return render(request, self.template_name, {
                'assignment': assignment,
                'subjects': subjects,
                'classes': classes,
                'action': 'Edit',
                'form_data': request.POST
            })

        assignment.title = title
        assignment.description = description
        assignment.due_date = due_date
        assignment.subject_id = subject_id
        assignment.student_class_id = class_id
        assignment.save()

        messages.success(request, "Assignment updated successfully.")
        return redirect('assignment_list')


@method_decorator([login_required], name='dispatch')
class AssignmentDeleteView(View):
    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        assignment = get_object_or_404(Assignment, pk=pk)

        if not request.user.is_staff and assignment.created_by != request.user.teacher:
            messages.error(request, "Access denied.")
            return redirect('assignment_list')

        assignment.delete()
        messages.success(request, "Assignment deleted successfully.")
        return redirect('assignment_list')


# ---- General Attendance Management (Admin/Teacher) ----

@method_decorator([login_required], name='dispatch')
class AttendanceListView(View):
    template_name = 'academics/attendance_list.html'

    def get(self, request):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        class_id = request.GET.get('class_id', '')
        subject_id = request.GET.get('subject_id', '')
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        qs = Attendance.objects.select_related('student__student_class', 'subject', 'marked_by__user').all()

        if not request.user.is_staff:
            teacher = request.user.teacher
            qs = qs.filter(student__student_class__teaching_assignments__teacher=teacher).distinct()

        if class_id:
            qs = qs.filter(student__student_class_id=class_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

        qs = qs.order_by('-date', 'student__regno')

        from django.core.paginator import Paginator
        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if request.user.is_staff:
            classes = Class.objects.select_related('department').all()
            subjects = Subject.objects.select_related('department').all()
        else:
            teacher = request.user.teacher
            classes = Class.objects.filter(teaching_assignments__teacher=teacher).distinct()
            subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()

        query_params = request.GET.copy()
        if 'page' in query_params:
            del query_params['page']

        return render(request, self.template_name, {
            'page_obj': page_obj,
            'classes': classes,
            'subjects': subjects,
            'selected_class': class_id,
            'selected_subject': subject_id,
            'start_date': start_date,
            'end_date': end_date,
            'query_params': query_params.urlencode()
        })


@method_decorator([login_required], name='dispatch')
class AttendanceDeleteView(View):
    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        record = get_object_or_404(Attendance, pk=pk)

        if not request.user.is_staff:
            teacher = request.user.teacher
            is_authorized = TeacherSubjectClass.objects.filter(
                teacher=teacher,
                student_class=record.student.student_class
            ).exists()
            if not is_authorized:
                messages.error(request, "Access denied.")
                return redirect('attendance_list')

        record.delete()
        messages.success(request, "Attendance record removed.")
        return redirect('attendance_list')


# ---- Marks Management (Admin/Teacher) ----

@method_decorator([login_required, teacher_required], name='dispatch')
class MarksBulkCreateView(View):
    template_name = 'academics/marks_bulk_add.html'

    def get(self, request):
        if request.user.is_staff:
            departments = Department.objects.all()
            classes = Class.objects.select_related('department').all()
            subjects = Subject.objects.select_related('department').all()
        else:
            teacher = request.user.teacher
            classes = Class.objects.filter(teaching_assignments__teacher=teacher).distinct()
            subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()
            departments = Department.objects.filter(classes__in=classes).distinct()

        class_id = request.GET.get('class_id', '')
        subject_id = request.GET.get('subject_id', '')
        exam_type = request.GET.get('exam_type', '')
        date = request.GET.get('date', '')

        students = []
        existing_marks = {}
        max_marks_default = 100

        if class_id and subject_id and exam_type:
            students = list(Student.objects.filter(student_class_id=class_id, is_active=True).order_by('regno'))
            marks_qs = Mark.objects.filter(
                student__student_class_id=class_id,
                subject_id=subject_id,
                exam_type=exam_type
            )
            if marks_qs.exists():
                max_marks_default = marks_qs.first().max_marks
                existing_marks = {m.student_id: m.marks_obtained for m in marks_qs}
            for student in students:
                student.existing_mark = existing_marks.get(student.pk)

        exam_types = Mark.EXAM_TYPE_CHOICES

        return render(request, self.template_name, {
            'departments': departments,
            'classes': classes,
            'subjects': subjects,
            'exam_types': exam_types,
            'students': students,
            'selected_class': class_id,
            'selected_subject': subject_id,
            'selected_exam_type': exam_type,
            'selected_date': date,
            'existing_marks': existing_marks,
            'max_marks_default': max_marks_default,
        })

    def post(self, request):
        class_id = request.POST.get('class_id', '')
        subject_id = request.POST.get('subject_id', '')
        exam_type = request.POST.get('exam_type', '')
        date = request.POST.get('date', '')
        max_marks_val = request.POST.get('max_marks', '').strip()

        if not request.user.is_staff:
            teacher = request.user.teacher
            authorized = TeacherSubjectClass.objects.filter(
                teacher=teacher,
                student_class_id=class_id,
                subject_id=subject_id
            ).exists()
            if not authorized:
                messages.error(request, "You are not assigned to teach this class/subject.")
                return redirect('marks_bulk_add')

        if not class_id or not subject_id or not exam_type or not date or not max_marks_val:
            messages.error(request, "Class, subject, exam type, date and max marks are required.")
            return redirect('marks_bulk_add')

        try:
            max_marks = float(max_marks_val)
        except ValueError:
            messages.error(request, "Invalid max marks.")
            return redirect('marks_bulk_add')

        students = Student.objects.filter(student_class_id=class_id, is_active=True)

        from django.db import transaction
        created, updated = 0, 0
        with transaction.atomic():
            for student in students:
                obt_val = request.POST.get(f'marks_{student.pk}', '').strip()
                if not obt_val:
                    continue
                try:
                    marks_obtained = float(obt_val)
                except ValueError:
                    continue
                
                if marks_obtained > max_marks:
                    messages.error(request, f"Marks for student {student.name} cannot exceed max marks ({max_marks}).")
                    # Build query string to return user to correct filtered state
                    return redirect(f'/manage/marks/add/?class_id={class_id}&subject_id={subject_id}&exam_type={exam_type}&date={date}')

                _, was_created = Mark.objects.update_or_create(
                    student=student,
                    subject_id=subject_id,
                    exam_type=exam_type,
                    defaults={
                        'marks_obtained': marks_obtained,
                        'max_marks': max_marks,
                        'date': date
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        messages.success(request, f"Marks saved: {created} new, {updated} updated.")
        return redirect('marks_list')


@method_decorator([login_required], name='dispatch')
class MarksListView(View):
    template_name = 'academics/marks_list.html'

    def get(self, request):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        dept_id = request.GET.get('department_id', '')
        class_id = request.GET.get('class_id', '')
        subject_id = request.GET.get('subject_id', '')
        exam_type = request.GET.get('exam_type', '')

        qs = Mark.objects.select_related('student__student_class__department', 'subject').all()

        if not request.user.is_staff:
            teacher = request.user.teacher
            qs = qs.filter(student__student_class__teaching_assignments__teacher=teacher).distinct()

        if dept_id:
            qs = qs.filter(student__student_class__department_id=dept_id)
        if class_id:
            qs = qs.filter(student__student_class_id=class_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if exam_type:
            qs = qs.filter(exam_type=exam_type)

        qs = qs.order_by('-date', 'student__regno')

        from django.core.paginator import Paginator
        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if request.user.is_staff:
            departments = Department.objects.all()
            classes = Class.objects.select_related('department').all()
            subjects = Subject.objects.select_related('department').all()
        else:
            teacher = request.user.teacher
            classes = Class.objects.filter(teaching_assignments__teacher=teacher).distinct()
            subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()
            departments = Department.objects.filter(classes__in=classes).distinct()

        exam_types = Mark.EXAM_TYPE_CHOICES

        query_params = request.GET.copy()
        if 'page' in query_params:
            del query_params['page']

        return render(request, self.template_name, {
            'page_obj': page_obj,
            'departments': departments,
            'classes': classes,
            'subjects': subjects,
            'exam_types': exam_types,
            'selected_dept': dept_id,
            'selected_class': class_id,
            'selected_subject': subject_id,
            'selected_exam_type': exam_type,
            'query_params': query_params.urlencode()
        })


@method_decorator([login_required], name='dispatch')
class MarksEditView(View):
    template_name = 'academics/marks_form.html'

    def get(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        mark = get_object_or_404(Mark, pk=pk)

        if not request.user.is_staff:
            teacher = request.user.teacher
            authorized = TeacherSubjectClass.objects.filter(
                teacher=teacher,
                student_class=mark.student.student_class,
                subject=mark.subject
            ).exists()
            if not authorized:
                messages.error(request, "Access denied.")
                return redirect('marks_list')

        if request.user.is_staff:
            subjects = Subject.objects.all()
        else:
            teacher = request.user.teacher
            subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()

        exam_types = Mark.EXAM_TYPE_CHOICES

        return render(request, self.template_name, {
            'mark': mark,
            'subjects': subjects,
            'exam_types': exam_types,
            'action': 'Edit',
            'form_data': {}
        })

    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        mark = get_object_or_404(Mark, pk=pk)

        if not request.user.is_staff:
            teacher = request.user.teacher
            authorized = TeacherSubjectClass.objects.filter(
                teacher=teacher,
                student_class=mark.student.student_class,
                subject=mark.subject
            ).exists()
            if not authorized:
                messages.error(request, "Access denied.")
                return redirect('marks_list')

        subject_id = request.POST.get('subject', '')
        exam_type = request.POST.get('exam_type', '')
        date = request.POST.get('date', '')
        obt_val = request.POST.get('marks_obtained', '').strip()
        max_val = request.POST.get('max_marks', '').strip()

        if not subject_id or not exam_type or not date or not obt_val or not max_val:
            messages.error(request, "All fields are required.")
            if request.user.is_staff:
                subjects = Subject.objects.all()
            else:
                teacher = request.user.teacher
                subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()
            exam_types = Mark.EXAM_TYPE_CHOICES
            return render(request, self.template_name, {
                'mark': mark,
                'subjects': subjects,
                'exam_types': exam_types,
                'action': 'Edit',
                'form_data': request.POST
            })

        try:
            marks_obtained = float(obt_val)
            max_marks = float(max_val)
            if marks_obtained > max_marks:
                raise ValueError("Marks obtained cannot exceed max marks.")
        except ValueError as e:
            messages.error(request, str(e) or "Invalid numeric values for marks.")
            if request.user.is_staff:
                subjects = Subject.objects.all()
            else:
                teacher = request.user.teacher
                subjects = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()
            exam_types = Mark.EXAM_TYPE_CHOICES
            return render(request, self.template_name, {
                'mark': mark,
                'subjects': subjects,
                'exam_types': exam_types,
                'action': 'Edit',
                'form_data': request.POST
            })

        mark.subject_id = subject_id
        mark.exam_type = exam_type
        mark.date = date
        mark.marks_obtained = marks_obtained
        mark.max_marks = max_marks
        mark.save()

        messages.success(request, "Marks record updated.")
        return redirect('marks_list')


@method_decorator([login_required], name='dispatch')
class MarksDeleteView(View):
    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        mark = get_object_or_404(Mark, pk=pk)

        if not request.user.is_staff:
            teacher = request.user.teacher
            authorized = TeacherSubjectClass.objects.filter(
                teacher=teacher,
                student_class=mark.student.student_class,
                subject=mark.subject
            ).exists()
            if not authorized:
                messages.error(request, "Access denied.")
                return redirect('marks_list')

        mark.delete()
        messages.success(request, "Marks record deleted.")
        return redirect('marks_list')


@method_decorator([login_required], name='dispatch')
class StudentAssignmentSubmitView(View):
    template_name = 'academics/student_assignment_submit.html'

    def get(self, request, pk):
        if not hasattr(request.user, 'student_profile'):
            messages.error(request, "Student access required.")
            return redirect('dashboard')
        
        student = request.user.student_profile
        assignment = get_object_or_404(Assignment, pk=pk)
        
        if assignment.student_class != student.student_class:
            messages.error(request, "Access denied. This assignment is not for your class.")
            return redirect('dashboard')
            
        from django.utils import timezone
        if assignment.due_date < timezone.now():
            messages.error(request, "This assignment is closed. The due date has passed.")
            return redirect('dashboard')
            
        from academics.models import Submission
        try:
            submission = Submission.objects.get(assignment=assignment, student=student)
        except Submission.DoesNotExist:
            submission = None

        return render(request, self.template_name, {
            'assignment': assignment,
            'submission': submission,
        })

    def post(self, request, pk):
        if not hasattr(request.user, 'student_profile'):
            messages.error(request, "Student access required.")
            return redirect('dashboard')
            
        student = request.user.student_profile
        assignment = get_object_or_404(Assignment, pk=pk)
        
        if assignment.student_class != student.student_class:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
            
        from django.utils import timezone
        if assignment.due_date < timezone.now():
            messages.error(request, "This assignment is closed. The due date has passed.")
            return redirect('dashboard')
            
        file_obj = request.FILES.get('file')
        if not file_obj:
            messages.error(request, "Please select a file to upload.")
            from academics.models import Submission
            return render(request, self.template_name, {
                'assignment': assignment,
                'submission': Submission.objects.filter(assignment=assignment, student=student).first()
            })
            
        from academics.models import Submission
        sub, created = Submission.objects.update_or_create(
            assignment=assignment,
            student=student,
            defaults={
                'file': file_obj,
                'submitted_at': timezone.now()
            }
        )
        if not created:
            sub.submitted_at = timezone.now()
            sub.save()
            
        messages.success(request, "Assignment submitted successfully!")
        return redirect('dashboard')


@method_decorator([login_required], name='dispatch')
class TeacherAssignmentSubmissionsView(View):
    template_name = 'academics/teacher_assignment_submissions.html'

    def get(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        assignment = get_object_or_404(Assignment, pk=pk)

        if not request.user.is_staff and assignment.created_by != request.user.teacher:
            messages.error(request, "Access denied. You do not own this assignment.")
            return redirect('assignment_list')

        students = Student.objects.filter(student_class=assignment.student_class, is_active=True).order_by('name')
        
        from academics.models import Submission
        submissions_dict = {
            s.student_id: s 
            for s in Submission.objects.filter(assignment=assignment)
        }

        return render(request, self.template_name, {
            'assignment': assignment,
            'students': students,
            'submissions': submissions_dict,
        })

    def post(self, request, pk):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            messages.error(request, "Access denied.")
            return redirect('dashboard')

        assignment = get_object_or_404(Assignment, pk=pk)

        if not request.user.is_staff and assignment.created_by != request.user.teacher:
            messages.error(request, "Access denied.")
            return redirect('assignment_list')

        students = Student.objects.filter(student_class=assignment.student_class, is_active=True)
        
        updated_count = 0
        from decimal import Decimal, InvalidOperation
        from academics.models import Submission
        
        for student in students:
            sub = Submission.objects.filter(assignment=assignment, student=student).first()
            if sub:
                grade_str = request.POST.get(f'grade_{student.id}', '').strip()
                feedback_val = request.POST.get(f'feedback_{student.id}', '').strip() or None
                
                if grade_str:
                    try:
                        sub.grade = Decimal(grade_str)
                    except (InvalidOperation, ValueError):
                        messages.error(request, f"Invalid grade value '{grade_str}' for student {student.name}.")
                        continue
                else:
                    sub.grade = None
                
                sub.feedback = feedback_val
                sub.save()
                updated_count += 1

        messages.success(request, f"Updated grading for {updated_count} submissions.")
        return redirect('teacher_assignment_submissions', pk=pk)




