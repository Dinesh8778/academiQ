from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.contrib.auth.models import User

from .models import Student
from academics.models import Class


def admin_or_teacher(request):
    return request.user.is_staff or hasattr(request.user, 'teacher')


@method_decorator(login_required, name='dispatch')
class StudentListView(View):
    def get(self, request):
        if not admin_or_teacher(request):
            messages.error(request, "Access denied.")
            return redirect('dashboard')
        qs = Student.objects.select_related('student_class__department').all()
        class_id = request.GET.get('class_id', '')
        if class_id:
            qs = qs.filter(student_class_id=class_id)
        return render(request, 'students/student_list.html', {
            'students': qs,
            'classes': Class.objects.select_related('department').all(),
            'selected_class': class_id,
        })


@method_decorator(login_required, name='dispatch')
class StudentCreateView(View):
    template_name = 'students/student_form.html'

    def get(self, request):
        if not admin_or_teacher(request):
            return redirect('dashboard')
        return render(request, self.template_name, {
            'classes': Class.objects.select_related('department').all(),
            'action': 'Create',
            'form_data': {},
        })

    def post(self, request):
        if not admin_or_teacher(request):
            return redirect('dashboard')
        regno = request.POST.get('regno', '').strip()
        name = request.POST.get('name', '').strip()
        class_id = request.POST.get('student_class', '')
        email = request.POST.get('email', '').strip() or None
        phone = request.POST.get('phone', '').strip() or None
        gender = request.POST.get('gender', '') or None
        guardian = request.POST.get('guardian_name', '').strip() or None
        if not regno or not name or not class_id:
            messages.error(request, "Register number, name, and class are required.")
            return render(request, self.template_name, {
                'classes': Class.objects.select_related('department').all(),
                'form_data': request.POST, 'action': 'Create'})
        if Student.objects.filter(regno=regno).exists():
            messages.error(request, "Register number already exists.")
            return render(request, self.template_name, {
                'classes': Class.objects.select_related('department').all(),
                'form_data': request.POST, 'action': 'Create'})
        Student.objects.create(
            regno=regno, name=name, student_class_id=class_id,
            email=email, phone=phone, gender=gender, guardian_name=guardian)
        messages.success(request, f"Student '{regno}' created.")
        return redirect('student_list')


@method_decorator(login_required, name='dispatch')
class StudentEditView(View):
    template_name = 'students/student_form.html'

    def get(self, request, pk):
        if not admin_or_teacher(request):
            return redirect('dashboard')
        student = get_object_or_404(Student, pk=pk)
        
        credential_logs = []
        if request.user.is_staff and student.user:
            from users.models import CredentialChangeLog
            credential_logs = CredentialChangeLog.objects.filter(target_user=student.user).order_by('-timestamp')

        submissions = student.submissions.select_related('assignment__subject').all()
        return render(request, self.template_name, {
            'classes': Class.objects.select_related('department').all(),
            'student': student,
            'action': 'Edit',
            'form_data': {},
            'credential_logs': credential_logs,
            'submissions': submissions
        })

    def post(self, request, pk):
        if not admin_or_teacher(request):
            return redirect('dashboard')
        student = get_object_or_404(Student, pk=pk)

        # 403 security check: non-admin trying to edit credentials
        has_cred_fields = any(field in request.POST for field in ['username', 'password', 'confirm_password'])
        if has_cred_fields and not request.user.is_staff:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can modify account credentials.")

        student.name = request.POST.get('name', student.name).strip()
        student.student_class_id = request.POST.get('student_class', student.student_class_id)
        student.email = request.POST.get('email', '').strip() or None
        student.phone = request.POST.get('phone', '').strip() or None
        student.gender = request.POST.get('gender', '') or None
        student.guardian_name = request.POST.get('guardian_name', '').strip() or None
        student.is_active = request.POST.get('is_active') == 'on'

        errors = []
        if not student.name or not student.student_class_id:
            errors.append("Name and class are required.")

        # Credentials-related validation
        new_username = request.POST.get('username', '').strip() if 'username' in request.POST else (student.user.username if student.user else '')
        new_password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        if request.user.is_staff and student.user:
            username_changed = new_username != student.user.username
            password_changed = bool(new_password)
            
            if username_changed:
                if not new_username:
                    errors.append("Username cannot be empty.")
                elif User.objects.exclude(pk=student.user.pk).filter(username=new_username).exists():
                    errors.append("Username is already taken.")
            
            if password_changed:
                if new_password != confirm_password:
                    errors.append("Passwords do not match.")
                else:
                    try:
                        from django.contrib.auth.password_validation import validate_password
                        from django.core.exceptions import ValidationError
                        validate_password(new_password, user=student.user)
                    except ValidationError as ve:
                        errors.extend(ve.messages)

        if errors:
            for err in errors:
                messages.error(request, err)
            
            credential_logs = []
            if request.user.is_staff and student.user:
                from users.models import CredentialChangeLog
                credential_logs = CredentialChangeLog.objects.filter(target_user=student.user).order_by('-timestamp')

            return render(request, self.template_name, {
                'classes': Class.objects.select_related('department').all(),
                'student': student,
                'form_data': request.POST,
                'action': 'Edit',
                'credential_logs': credential_logs
            })

        # Save credentials first
        if request.user.is_staff and student.user:
            from users.utils import update_user_credentials
            update_user_credentials(request, student.user, new_username, new_password, confirm_password)

        student.save()
        messages.success(request, "Student updated.")
        return redirect('student_list')


@method_decorator(login_required, name='dispatch')
class StudentDeleteView(View):
    def post(self, request, pk):
        if not request.user.is_staff:
            messages.error(request, "Admin only.")
            return redirect('dashboard')
        get_object_or_404(Student, pk=pk).delete()
        messages.success(request, "Student deleted.")
        return redirect('student_list')
