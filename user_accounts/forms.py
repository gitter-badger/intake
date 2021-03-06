from django import forms
from invitations.forms import InviteForm as BaseInviteForm
from allauth.account import forms as allauth_forms
from . import models, exceptions


class LoginForm(allauth_forms.LoginForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        error_message = "Sorry, that email and password do not work together"
        self.error_messages['email_password_mismatch'] = error_message


class InviteForm(BaseInviteForm):

    organization = forms.ModelChoiceField(
        label="Organization",
        required=True,
        queryset=models.Organization.objects.all(),
        empty_label=None)

    def save(self, inviter=None):
        return models.Invitation.create(
            email=self.cleaned_data['email'],
            organization=self.cleaned_data['organization'],
            inviter=inviter)


class UserProfileForm(forms.ModelForm):

    class Meta:
        model = models.UserProfile
        fields = ['name']


class CustomSignUpForm(allauth_forms.SignupForm):
    name = forms.CharField(max_length=200, label='Name',
                           required=False)

    def custom_signup(self, request, user):
        super().custom_signup(request, user)
        models.UserProfile.create_from_invited_user(
            user=user,
            name=self.cleaned_data['name']
        )


class SetPasswordForm(forms.Form):

    password = allauth_forms.SetPasswordField(
        label="New Password")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.temp_key = kwargs.pop("temp_key", None)
        super().__init__(*args, **kwargs)

    def save(self):
        allauth_forms.get_adapter().set_password(
            self.user, self.cleaned_data['password']
            )





