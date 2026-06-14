from django.apps import AppConfig


class StandsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stands'

    def ready(self):
        # This app keys identity on EMAIL (SOCIALACCOUNT_EMAIL_AUTHENTICATION);
        # allauth's auto-generated username is a lowercased, throwaway artifact.
        # The default User model can't be subclassed on a live project without a
        # risky AUTH_USER_MODEL swap, so we adjust how a User stringifies — which
        # is what the admin renders for FK columns, readonly fields, and select
        # widgets (owner, created_by, updated_by, photo uploaded_by, etc.).
        # SAFE: no public template renders str(user) (they use .id / .first_name),
        # so emails are never exposed outside the admin. The login flash uses
        # ACCOUNT_USER_DISPLAY (first name) and is unaffected.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.add_to_class(
            '__str__',
            lambda self: (self.email or self.get_full_name()
                          or self.get_username()))
