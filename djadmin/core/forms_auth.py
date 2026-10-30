"""Формы регистрации, подтверждения email и сброса пароля (фаза 2б).

Паритет Flask: validate_password (≥8, заглавная, строчная, цифра, спецсимвол),
honeypot «website», согласие 152-ФЗ, intent → роль.
"""
import re

from django import forms

from .models import Profile

INPUT_CLS = "w-full border border-gray-300 rounded px-3 py-2 bg-white"

SPECIAL_RE = re.compile(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/]")


def validate_password(password: str) -> str | None:
    """Порт app/utils/validators.py: возвращает текст ошибки или None."""
    if len(password) < 8:
        return "Пароль должен содержать минимум 8 символов."
    if not re.search(r"[A-ZА-ЯЁ]", password):
        return "Пароль должен содержать заглавную букву."
    if not re.search(r"[a-zа-яё]", password):
        return "Пароль должен содержать строчную букву."
    if not re.search(r"\d", password):
        return "Пароль должен содержать цифру."
    if not SPECIAL_RE.search(password):
        return "Пароль должен содержать специальный символ (!@#$%^&* и т.п.)."
    return None


class RegisterForm(forms.Form):
    INTENT_CHOICES = (
        ("both", "Ищу подработку и размещаю задания"),
        ("find_work", "Ищу подработку"),
        ("post_jobs", "Размещаю задания"),
    )
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": INPUT_CLS}))
    full_name = forms.CharField(label="ФИО", max_length=300, widget=forms.TextInput(attrs={"class": INPUT_CLS}))
    city = forms.CharField(label="Город", max_length=200, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLS}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    intent = forms.ChoiceField(label="Цель", choices=INTENT_CHOICES, initial="both",
                               widget=forms.RadioSelect)
    consent = forms.BooleanField(label="Согласен с обработкой персональных данных (152-ФЗ)")
    website = forms.CharField(  # honeypot: люди это поле не видят/не заполняют
        required=False, widget=forms.HiddenInput,
    )
    smart_token = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        error = validate_password(password)
        if error:
            raise forms.ValidationError(error)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            # honeypот заполнен — тихо считаем форму невалидной (боту не сообщаем причину)
            raise forms.ValidationError("Регистрация невозможна.")
        return cleaned

    def role_and_visibility(self):
        intent = self.cleaned_data.get("intent", "both")
        if intent == "post_jobs":
            return Profile.Role.EMPLOYER, False
        return Profile.Role.WORKER, True


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": INPUT_CLS, "autofocus": True}))
    smart_token = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()


class PasswordResetConfirmForm(forms.Form):
    new_password = forms.CharField(label="Новый пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
    confirm_password = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))

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
