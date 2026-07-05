import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.contrib.messages import get_messages
from users.models import CredentialChangeLog


@pytest.mark.django_db
class TestCredentialReset:

    def test_admin_change_username_password_student(self, client, admin_user, student_user):
        client.force_login(admin_user)
        student = student_user.student_profile

        # Retrieve page first
        response = client.get(f'/manage/students/{student.pk}/edit/')
        assert response.status_code == 200
        assert "Account Credentials" in response.content.decode()

        # Update username and password
        response = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': 'Updated Name',
            'student_class': student.student_class.pk,
            'username': 'new_student_user',
            'password': 'SecurePass@123456',
            'confirm_password': 'SecurePass@123456',
        })
        assert response.status_code == 302  # redirects to student list

        # Verify database fields updated
        student_user.refresh_from_db()
        assert student_user.username == 'new_student_user'
        assert student_user.check_password('SecurePass@123456')

        # Verify audit log
        log = CredentialChangeLog.objects.first()
        assert log is not None
        assert log.admin == admin_user
        assert log.target_user == student_user
        assert log.action_type == 'both'

    def test_admin_change_username_password_teacher(self, client, admin_user, teacher_user):
        client.force_login(admin_user)
        teacher = teacher_user.teacher

        # Update username and password
        response = client.post(f'/manage/teachers/{teacher.pk}/edit/', {
            'teacher_id': teacher.teacher_id,
            'first_name': 'NewFirst',
            'last_name': 'NewLast',
            'username': 'new_teacher_user',
            'password': 'SecurePass@123456',
            'confirm_password': 'SecurePass@123456',
        })
        assert response.status_code == 302

        # Verify database fields updated
        teacher_user.refresh_from_db()
        assert teacher_user.username == 'new_teacher_user'
        assert teacher_user.check_password('SecurePass@123456')

        # Verify audit log
        log = CredentialChangeLog.objects.first()
        assert log is not None
        assert log.admin == admin_user
        assert log.target_user == teacher_user
        assert log.action_type == 'both'

    def test_teacher_attempt_change_credentials_student_denied(self, client, teacher_user, student_user):
        client.force_login(teacher_user)
        student = student_user.student_profile

        # 1. UI elements should not be visible to teachers
        response = client.get(f'/manage/students/{student.pk}/edit/')
        assert response.status_code == 200
        assert "Account Credentials" not in response.content.decode()

        # 2. Attempt post to change credentials => should raise PermissionDenied which resolves to 403
        response = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': student.name,
            'student_class': student.student_class.pk,
            'username': 'hacked_username',
            'password': 'SomePassword123',
            'confirm_password': 'SomePassword123',
        })
        assert response.status_code == 403

    def test_validation_weak_password_rejected(self, client, admin_user, student_user):
        client.force_login(admin_user)
        student = student_user.student_profile

        # Weak password post
        response = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': student.name,
            'student_class': student.student_class.pk,
            'username': student_user.username,
            'password': '123',
            'confirm_password': '123',
        })
        assert response.status_code == 200
        messages = [m.message for m in list(get_messages(response.wsgi_request))]
        assert any("password" in m.lower() or "too short" in m.lower() or "numeric" in m.lower() for m in messages)

        # Ensure password did NOT change
        student_user.refresh_from_db()
        assert not student_user.check_password('123')

    def test_validation_duplicate_username_rejected(self, client, admin_user, student_user, teacher_user):
        client.force_login(admin_user)
        student = student_user.student_profile

        # Duplicate username (student tries to get teacher's username)
        response = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': student.name,
            'student_class': student.student_class.pk,
            'username': teacher_user.username,
            'password': '',
            'confirm_password': '',
        })
        assert response.status_code == 200
        messages = [m.message for m in list(get_messages(response.wsgi_request))]
        assert any("already taken" in m.lower() for m in messages)

        student_user.refresh_from_db()
        assert student_user.username != teacher_user.username

    def test_jwt_refresh_tokens_blacklisted_on_password_change(self, client, admin_user, student_user):
        # Create a simplejwt Token first by forcing generation
        refresh = RefreshToken.for_user(student_user)
        jti = refresh.payload['jti']

        # Verify it exists as an outstanding token
        assert OutstandingToken.objects.filter(jti=jti).exists()

        # Admin logs in and updates student pass
        client.force_login(admin_user)
        student = student_user.student_profile
        response = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': student.name,
            'student_class': student.student_class.pk,
            'username': student_user.username,
            'password': 'SecurePass@123456',
            'confirm_password': 'SecurePass@123456',
        })
        assert response.status_code == 302

        # Check outstanding token is blacklist-registered
        assert BlacklistedToken.objects.filter(token__jti=jti).exists()
