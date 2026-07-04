"""
Custom DRF permission classes for role-based access control.

Roles are determined by the related model attached to auth.User:
  - Admin:   user.is_staff  (Django built-in superuser/staff flag)
  - Teacher: hasattr(user, 'teacher') — Teacher.user OneToOne exists
  - Student: hasattr(user, 'student_profile') — Student.user OneToOne exists
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    """Allow access only to staff/superuser accounts."""

    message = "You must be an administrator to perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsTeacher(BasePermission):
    """Allow access only to users with an attached Teacher profile."""

    message = "You must be a teacher to perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'teacher')
        )


class IsStudent(BasePermission):
    """Allow access only to users with an attached Student profile."""

    message = "You must be a student to perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'student_profile')
        )


class IsAdminOrTeacher(BasePermission):
    """Allow access to admins or teachers."""

    message = "You must be an administrator or teacher to perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.user.is_staff or hasattr(request.user, 'teacher')


class IsOwnerOrReadOnly(BasePermission):
    """
    Object-level permission for Submission objects.
    - Safe (GET/HEAD/OPTIONS): any authenticated user.
    - Unsafe (POST/PUT/PATCH/DELETE): only the student who owns the submission,
      or an admin/teacher.
    """

    message = "You do not have permission to modify this submission."

    def has_object_permission(self, request, view, obj):
        # Safe methods are always allowed for authenticated users
        if request.method in SAFE_METHODS:
            return True

        # Admins and teachers can always modify
        if request.user.is_staff or hasattr(request.user, 'teacher'):
            return True

        # Students can only modify their own submission
        if hasattr(request.user, 'student_profile'):
            return obj.student == request.user.student_profile

        return False
