"""
Template views + API views for users/auth app.
"""
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.db.models import Count, Q

from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    CustomTokenObtainPairSerializer,
    TeacherRegistrationSerializer,
    StudentRegistrationSerializer,
    UserProfileSerializer,
    TeacherSerializer,
)
from .permissions import IsAdmin, IsAdminOrTeacher
from .models import Teacher


# ===========================================================================
# Auth views
# ===========================================================================

class LoginPageView(View):
    template_name = 'auth/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "Invalid username or password.")
            return render(request, self.template_name, {'username': username})
        login(request, user)
        return redirect('dashboard')


class LogoutView(View):
    def post(self, request):
        logout(request)
        messages.success(request, "You have been logged out.")
        return redirect('login')


@method_decorator(login_required, name='dispatch')
class DashboardRedirectView(View):
    def get(self, request):
        user = request.user
        if user.is_staff:
            return redirect('admin_dashboard')
        if hasattr(user, 'teacher'):
            return redirect('teacher_dashboard')
        if hasattr(user, 'student_profile'):
            return redirect('student_dashboard')
        return render(request, 'auth/no_profile.html')


# ===========================================================================
# Admin Dashboard
# ===========================================================================

@method_decorator(login_required, name='dispatch')
class AdminDashboardView(View):
    template_name = 'dashboard/admin.html'

    def get(self, request):
        if not request.user.is_staff:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        from students.models import Student
        from academics.models import Class, Department, Subject
        from attendance.models import Attendance
        context = {
            'student_count': Student.objects.filter(is_active=True).count(),
            'teacher_count': Teacher.objects.count(),
            'class_count': Class.objects.count(),
            'dept_count': Department.objects.count(),
            'subject_count': Subject.objects.count(),
            'recent_students': Student.objects.select_related(
                'student_class__department').order_by('-id')[:5],
            'recent_teachers': Teacher.objects.select_related(
                'user', 'department').order_by('-id')[:5],
        }

        # AI risk scores — graceful fallback if model not trained yet
        try:
            from ai_engine.predictor import predict_risk
            all_results = predict_risk()
            context['ai_risk_students'] = [
                r for r in all_results if r['at_risk_label'] == 1
            ][:15]
            context['ai_total_students'] = len(all_results)
        except Exception:
            context['ai_risk_students'] = None
            context['ai_total_students'] = 0

        # Department exam performance comparison
        try:
            from assistant.tools import get_department_exam_comparison
            from academics.models import Mark
            selected_comparison_exam = request.GET.get('comparison_exam_type', 'END')
            comparison_results = get_department_exam_comparison(request.user, selected_comparison_exam)
            context['comparison_exam_types'] = Mark.EXAM_TYPE_CHOICES
            context['selected_comparison_exam'] = selected_comparison_exam
            context['comparison_results'] = comparison_results.get('comparison', [])
        except Exception:
            context['comparison_results'] = []

        return render(request, self.template_name, context)


# ===========================================================================
# Teacher Dashboard
# ===========================================================================

@method_decorator(login_required, name='dispatch')
class TeacherDashboardView(View):
    template_name = 'dashboard/teacher.html'

    def get(self, request):
        if not hasattr(request.user, 'teacher'):
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        teacher = request.user.teacher
        from academics.models import Assignment, Submission, TeacherSubjectClass
        from django.utils import timezone
        teaching = TeacherSubjectClass.objects.filter(
            teacher=teacher).select_related('subject', 'student_class__department')
        assignments = Assignment.objects.filter(
            created_by=teacher).select_related(
            'subject', 'student_class').order_by('-created_at')[:10]
        pending_submissions = Submission.objects.filter(
            assignment__created_by=teacher,
            grade__isnull=True,
            file__isnull=False,
        ).select_related('student', 'assignment')[:10]
        context = {
            'teacher': teacher,
            'teaching': teaching,
            'assignments': assignments,
            'pending_submissions': pending_submissions,
            'advised_classes': teacher.advised_classes.select_related('department').all(),
            'now': timezone.now(),
        }

        # AI risk scores — graceful fallback if model not trained yet
        try:
            from ai_engine.predictor import predict_risk
            all_results = predict_risk()
            # Only show students from classes this teacher teaches
            taught_class_ids = set(
                teaching.values_list('student_class_id', flat=True)
            )
            context['ai_risk_students'] = [
                r for r in all_results
                if r['at_risk_label'] == 1
            ][:10]
        except Exception:
            context['ai_risk_students'] = None  # model not trained yet

        return render(request, self.template_name, context)


# ===========================================================================
# Student Dashboard
# ===========================================================================

@method_decorator(login_required, name='dispatch')
class StudentDashboardView(View):
    template_name = 'dashboard/student.html'

    def get(self, request):
        if not hasattr(request.user, 'student_profile'):
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        student = request.user.student_profile
        from attendance.models import Attendance
        from academics.models import Assignment, Mark

        att_records = Attendance.objects.filter(student=student)
        total_att = att_records.count()
        present_att = att_records.filter(status=True).count()
        att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0

        assignments = Assignment.objects.filter(
            student_class=student.student_class
        ).select_related('subject').order_by('-due_date')[:10]

        from academics.models import Submission
        my_submissions = {
            s.assignment_id: s
            for s in Submission.objects.filter(student=student)
        }

        marks = Mark.objects.filter(student=student).select_related('subject')
        total_obt = sum(float(m.marks_obtained) for m in marks)
        total_max = sum(float(m.max_marks) for m in marks)
        overall_pct = round((total_obt / total_max * 100), 1) if total_max > 0 else 0

        from django.utils import timezone
        context = {
            'student': student,
            'att_pct': att_pct,
            'total_att': total_att,
            'present_att': present_att,
            'absent_att': total_att - present_att,
            'assignments': assignments,
            'my_submissions': my_submissions,
            'marks': marks,
            'overall_pct': overall_pct,
            'now': timezone.now(),
        }
        return render(request, self.template_name, context)


# ===========================================================================
# Registration pages
# ===========================================================================

class TeacherRegisterPageView(View):
    template_name = 'auth/register_teacher.html'

    def get(self, request):
        from academics.models import Department
        return render(request, self.template_name, {'departments': Department.objects.all()})

    def post(self, request):
        from academics.models import Department
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        teacher_id = request.POST.get('teacher_id', '').strip()
        department_id = request.POST.get('department', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        errors = []
        if password != password2:
            errors.append("Passwords do not match.")
        if User.objects.filter(username=username).exists():
            errors.append("Username already taken.")
        if Teacher.objects.filter(teacher_id=teacher_id).exists():
            errors.append("Teacher ID already exists.")
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, self.template_name, {
                'departments': Department.objects.all(), 'form_data': request.POST})
        user = User.objects.create_user(
            username=username, password=password,
            email=email, first_name=first_name, last_name=last_name)
        Teacher.objects.create(
            user=user, teacher_id=teacher_id,
            department=Department.objects.get(pk=department_id))
        messages.success(request, f"Teacher '{username}' created.")
        return redirect('login')


class StudentRegisterPageView(View):
    template_name = 'auth/register_student.html'

    def get(self, request):
        from academics.models import Class
        return render(request, self.template_name,
                      {'classes': Class.objects.select_related('department').all()})

    def post(self, request):
        from academics.models import Class
        from students.models import Student
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        regno = request.POST.get('regno', '').strip()
        name = request.POST.get('name', '').strip()
        class_id = request.POST.get('student_class', '')
        email = request.POST.get('email', '').strip()
        errors = []
        if password != password2:
            errors.append("Passwords do not match.")
        if User.objects.filter(username=username).exists():
            errors.append("Username already taken.")
        if Student.objects.filter(regno=regno).exists():
            errors.append("Register number already exists.")
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, self.template_name, {
                'classes': Class.objects.select_related('department').all(),
                'form_data': request.POST})
        user = User.objects.create_user(username=username, password=password, email=email)
        Student.objects.create(user=user, regno=regno, name=name,
            student_class=Class.objects.get(pk=class_id), email=email or None)
        messages.success(request, f"Student '{username}' created.")
        return redirect('login')


# ===========================================================================
# API views (JWT)
# ===========================================================================

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    pass


class TokenLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({"detail": "Refresh token required."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TeacherRegisterAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Admin only."}, status=status.HTTP_403_FORBIDDEN)
        s = TeacherRegistrationSerializer(data=request.data)
        if s.is_valid():
            t = s.save()
            return Response({"detail": "Created.", "teacher_id": t.teacher_id},
                            status=status.HTTP_201_CREATED)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentRegisterAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not (request.user.is_staff or hasattr(request.user, 'teacher')):
            return Response({"detail": "Admin or teacher only."}, status=status.HTTP_403_FORBIDDEN)
        s = StudentRegistrationSerializer(data=request.data)
        if s.is_valid():
            st = s.save()
            return Response({"detail": "Created.", "regno": st.regno},
                            status=status.HTTP_201_CREATED)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)


# ===========================================================================
# Teacher ViewSet (API)
# ===========================================================================

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.select_related('user', 'department').all()
    serializer_class = TeacherSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAdminOrTeacher()]
        return [IsAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff and hasattr(user, 'teacher'):
            qs = qs.filter(pk=user.teacher.pk)
        return qs


# ===========================================================================
# Root home redirect  (handles GET /)
# ===========================================================================

def home_redirect(request):
    """
    Mounted at path('', ..., name='home') in root urls.py.

    Authenticated  → /auth/dashboard/  (which contains role-branching logic)
    Unauthenticated → /auth/login/
    """
    if request.user.is_authenticated:
        return redirect('dashboard')   # /auth/dashboard/ → DashboardRedirectView
    return redirect('login')           # /auth/login/


# ===========================================================================
# Teacher UI Views (Admin only)
# ===========================================================================

@method_decorator(login_required, name='dispatch')
class TeacherListView(View):
    def get(self, request):
        if not request.user.is_staff:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        teachers = Teacher.objects.select_related('user', 'department').all()
        groups = []
        from academics.models import Department
        for dept in Department.objects.all():
            dept_teachers = [t for t in teachers if t.department_id == dept.pk]
            if dept_teachers:
                groups.append({
                    'department': dept,
                    'teachers': dept_teachers
                })
        unassigned = [t for t in teachers if t.department is None]
        if unassigned:
            groups.append({
                'department': None,
                'teachers': unassigned
            })
        return render(request, 'users/teacher_list.html', {'groups': groups})


@method_decorator(login_required, name='dispatch')
class TeacherEditView(View):
    template_name = 'users/teacher_form.html'

    def get(self, request, pk):
        if not request.user.is_staff:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        teacher = get_object_or_404(Teacher, pk=pk)
        from academics.models import Department
        
        credential_logs = []
        if request.user.is_staff and teacher.user:
            from users.models import CredentialChangeLog
            credential_logs = CredentialChangeLog.objects.filter(target_user=teacher.user).order_by('-timestamp')

        return render(request, self.template_name, {
            'departments': Department.objects.all(),
            'teacher': teacher,
            'action': 'Edit',
            'form_data': {},
            'credential_logs': credential_logs
        })

    def post(self, request, pk):
        if not request.user.is_staff:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        teacher = get_object_or_404(Teacher, pk=pk)

        teacher_id = request.POST.get('teacher_id', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip() or None
        department_id = request.POST.get('department', '')

        errors = []
        if not teacher_id:
            errors.append("Teacher ID is required.")
        if Teacher.objects.exclude(pk=pk).filter(teacher_id=teacher_id).exists():
            errors.append("Teacher ID already exists.")

        # Credentials-related validation
        new_username = request.POST.get('username', '').strip() if 'username' in request.POST else (teacher.user.username if teacher.user else '')
        new_password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        if request.user.is_staff and teacher.user:
            username_changed = new_username != teacher.user.username
            password_changed = bool(new_password)
            
            if username_changed:
                if not new_username:
                    errors.append("Username cannot be empty.")
                elif User.objects.exclude(pk=teacher.user.pk).filter(username=new_username).exists():
                    errors.append("Username is already taken.")
            
            if password_changed:
                if new_password != confirm_password:
                    errors.append("Passwords do not match.")
                else:
                    try:
                        from django.contrib.auth.password_validation import validate_password
                        from django.core.exceptions import ValidationError
                        validate_password(new_password, user=teacher.user)
                    except ValidationError as ve:
                        errors.extend(ve.messages)

        if errors:
            for e in errors:
                messages.error(request, e)
            from academics.models import Department
            from users.models import CredentialChangeLog
            credential_logs = CredentialChangeLog.objects.filter(target_user=teacher.user).order_by('-timestamp')
            return render(request, self.template_name, {
                'departments': Department.objects.all(),
                'teacher': teacher,
                'form_data': request.POST,
                'action': 'Edit',
                'credential_logs': credential_logs
            })

        # Save credentials first
        if request.user.is_staff and teacher.user:
            from users.utils import update_user_credentials
            update_user_credentials(request, teacher.user, new_username, new_password, confirm_password)

        user = teacher.user
        user.first_name = first_name
        user.last_name = last_name
        user.email = email or ""
        user.save()

        teacher.teacher_id = teacher_id
        if department_id:
            from academics.models import Department
            teacher.department = get_object_or_404(Department, pk=department_id)
        else:
            teacher.department = None
        teacher.save()

        messages.success(request, "Teacher updated.")
        return redirect('teacher_list')


@method_decorator(login_required, name='dispatch')
class TeacherDeleteView(View):
    def post(self, request, pk):
        if not request.user.is_staff:
            messages.error(request, "Admin only.")
            return redirect('dashboard')
        teacher = get_object_or_404(Teacher, pk=pk)
        user = teacher.user
        teacher.delete()
        if user:
            user.delete()
        messages.success(request, "Teacher deleted.")
        return redirect('teacher_list')

