from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from users.models import CredentialChangeLog

def update_user_credentials(request, target_user, new_username, new_password, confirm_password):
    """
    Validates and updates credentials for a target_user.
    Returns: a list of error messages (if any). If empty, the update succeeded.
    """
    errors = []
    
    username_changed = new_username != target_user.username
    password_changed = bool(new_password)
    
    if not username_changed and not password_changed:
        return errors  # No changes requested

    if username_changed:
        if not new_username:
            errors.append("Username cannot be empty.")
        elif User.objects.exclude(pk=target_user.pk).filter(username=new_username).exists():
            errors.append("Username is already taken.")
            
    if password_changed:
        if new_password != confirm_password:
            errors.append("Passwords do not match.")
        else:
            try:
                validate_password(new_password, user=target_user)
            except ValidationError as ve:
                errors.extend(ve.messages)
                
    if errors:
        return errors
        
    # Perform the updates
    action_type = ""
    if username_changed:
        target_user.username = new_username
        action_type = "username"
    if password_changed:
        target_user.set_password(new_password)
        action_type = "both" if action_type else "password"
        
    target_user.save()
    
    # Blacklist outstanding simplejwt refresh tokens
    if password_changed:
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            for token in OutstandingToken.objects.filter(user=target_user):
                BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            pass
            
    # Create the change log
    CredentialChangeLog.objects.create(
        admin=request.user,
        target_user=target_user,
        action_type=action_type
    )
    
    return errors
