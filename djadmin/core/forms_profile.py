"""Формы фазы 2в: профиль, смена пароля."""
from django import forms
from django.utils.translation import gettext, gettext_lazy as _

from .forms_auth import INPUT_CLS, is_valid_contact, validate_inn_checksum, validate_password
from .models import EmployerDetail, Profile, Skill


class ProfileForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.order_by("sort_order", "name"),
        widget=forms.CheckboxSelectMultiple, required=False, label=_("Навыки"),
    )

    class Meta:
        model = Profile
        fields = (
            "full_name", "city", "phone", "age", "bio", "experience",
            "desired_payment", "portfolio_link", "contact", "email_public",
            "inn", "is_self_employed", "worker_visibility",
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

    def clean_inn(self):
        inn = (self.cleaned_data.get("inn") or "").strip()
        if not inn:
            return inn
        if not inn.isdigit() or len(inn) != 12:
            raise forms.ValidationError(gettext("ИНН должен содержать ровно 12 цифр."))
        if not validate_inn_checksum(inn):
            raise forms.ValidationError(gettext("Некорректный ИНН — проверьте контрольную сумму."))
        return inn

    def clean_contact(self):
        contact = (self.cleaned_data.get("contact") or "").strip()
        if not contact:
            return contact
        if len(contact) < 3:
            raise forms.ValidationError(gettext("Контакт должен содержать минимум 3 символа."))
        if not is_valid_contact(contact):
            raise forms.ValidationError(gettext("Введите корректный контакт: email, телефон или никнейм."))
        return contact


class EmployerDetailForm(forms.ModelForm):
    class Meta:
        model = EmployerDetail
        fields = ("name", "company_name", "city", "address", "description", "inn")
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLS}),
            "company_name": forms.TextInput(attrs={"class": INPUT_CLS}),
            "city": forms.TextInput(attrs={"class": INPUT_CLS}),
            "address": forms.TextInput(attrs={"class": INPUT_CLS}),
            "description": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 4}),
            "inn": forms.TextInput(attrs={"class": INPUT_CLS}),
        }

    def clean_inn(self):
        inn = (self.cleaned_data.get("inn") or "").strip()
        if inn and (not inn.isdigit() or len(inn) not in (10, 12)):
            raise forms.ValidationError(gettext("ИНН должен содержать 10 или 12 цифр."))
        return inn


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(label=_("Текущий пароль"), widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    new_password = forms.CharField(label=_("Новый пароль"), widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    confirm_password = forms.CharField(label=_("Повторите новый"), widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))

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
            raise forms.ValidationError(gettext("Пароли не совпадают."))
        return cleaned
