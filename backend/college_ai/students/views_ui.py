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
        return render(request, self.template_name, {
            'classes': Class.objects.select_related('department').all(),
            'student': student, 'action': 'Edit'})

    def post(self, request, pk):
        if not admin_or_teacher(request):
            return redirect('dashboard')
        student = get_object_or_404(Student, pk=pk)
        student.name = request.POST.get('name', student.name).strip()
        student.student_class_id = request.POST.get('student_class', student.student_class_id)
        student.email = request.POST.get('email', '').strip() or None
        student.phone = request.POST.get('phone', '').strip() or None
        student.gender = request.POST.get('gender', '') or None
        student.guardian_name = request.POST.get('guardian_name', '').strip() or None
        student.is_active = request.POST.get('is_active') == 'on'
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
