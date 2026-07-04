from django.urls import path
from django.contrib.auth import views as django_auth_views
from . import views

urlpatterns = [
    path('login/',     views.LoginPageView.as_view(),          name='login'),
    path('logout/',    views.LogoutView.as_view(),             name='logout'),
    path('dashboard/', views.DashboardRedirectView.as_view(),  name='dashboard'),

    path('dashboard/admin/',   views.AdminDashboardView.as_view(),   name='admin_dashboard'),
    path('dashboard/teacher/', views.TeacherDashboardView.as_view(), name='teacher_dashboard'),
    path('dashboard/student/', views.StudentDashboardView.as_view(), name='student_dashboard'),

    path('register/teacher/', views.TeacherRegisterPageView.as_view(), name='register_teacher'),
    path('register/student/', views.StudentRegisterPageView.as_view(), name='register_student'),

    path('password-reset/',
         django_auth_views.PasswordResetView.as_view(
             template_name='auth/password_reset.html',
             email_template_name='auth/email/password_reset_email.txt',
             subject_template_name='auth/email/password_reset_subject.txt'),
         name='password_reset'),
    path('password-reset/done/',
         django_auth_views.PasswordResetDoneView.as_view(
             template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/',
         django_auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password-reset/complete/',
         django_auth_views.PasswordResetCompleteView.as_view(
             template_name='auth/password_reset_complete.html'),
         name='password_reset_complete'),
]
