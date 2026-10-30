"""Формы фазы 2в: профиль, смена пароля."""
from django import forms

from .forms_auth import INPUT_CLS, validate_password
from .models import Profile, Skill


class ProfileForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.order_by("sort_order", "name"),
        widget=forms.CheckboxSelectMultiple, required=False, label="Навыки",
    )

    class Meta:
        model = Profile
        fields = (
            "full_name", "city", "phone", "age", "bio", "experience",
            "desired_payment", "portfolio_link", "contact", "email_public",
            "inn", "is_self_employed", "religion", "worker_visibility",
        )
        widgets = {
            "full_name": forms.TextInput(attrs={"class": INPUT_CLS}),
            "city": forms.TextInput(attrs={"class": INPUT_CLS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLS}),
            "age": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 14, "max": 120}),
            "bio": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 3}),
            "experience": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 3}),
            "desired_payment": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 0, "step": "0.01"}),
            "portfolio_link": forms.URLInput(attrs={"class": INPUT_CLS}),
            "contact": forms.TextInput(attrs={"class": INPUT_CLS}),
            "email_public": forms.EmailInput(attrs={"class": INPUT_CLS}),
            "inn": forms.TextInput(attrs={"class": INPUT_CLS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import UserSkill

        if self.instance and self.instance.pk:
            self.fields["skills"].initial = list(
                UserSkill.objects.filter(user=self.instance).values_list("skill_id", flat=True)
            )


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    new_password = forms.CharField(label="Новый пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    confirm_password = forms.CharField(label="Повторите новый", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password") or ""
        error = validate_password(password)
        if error:
            raise forms.ValidationError(error)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") and cleaned.get("confirm_password") and \
                cleaned["new_password"] != cleaned["confirm_password"]:
            raise forms.ValidationError("Пароли не совпадают.")
        return cleaned
