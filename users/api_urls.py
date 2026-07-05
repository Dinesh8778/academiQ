"""
API-only URL patterns for auth.
Mounted at /api/auth/ from the root urls.py
"""

from django.urls import path
from . import views

urlpatterns = [
    # JWT token obtain / refresh / logout
    path('token/',         views.CustomTokenObtainPairView.as_view(),  name='api_token_obtain'),
    path('token/refresh/', views.CustomTokenRefreshView.as_view(),     name='api_token_refresh'),
    path('token/logout/',  views.TokenLogoutView.as_view(),            name='api_token_logout'),

    # Registration endpoints
    path('register/teacher/', views.TeacherRegisterAPIView.as_view(),  name='api_register_teacher'),
    path('register/student/', views.StudentRegisterAPIView.as_view(),  name='api_register_student'),

    # Current user profile
    path('me/', views.MeView.as_view(), name='api_me'),
]
