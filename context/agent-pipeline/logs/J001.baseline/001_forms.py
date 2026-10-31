"""Формы пользовательских флоу (фаза 2а)."""
from django import forms

from .models import Job, JobSkill, Skill

INPUT_CLS = "w-full border border-gray-300 rounded px-3 py-2 bg-white"

JOB_FIELDS = (
    "work_type", "organization_name", "org_description", "object_description",
    "detailed_description", "address", "city", "payment_amount", "max_workers",
    "preferred_religion", "date_time",
)


class JobForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.order_by("sort_order", "name"),
        widget=forms.CheckboxSelectMultiple, required=False, label="Навыки",
    )

    class Meta:
        model = Job
        fields = JOB_FIELDS
        widgets = {
            "work_type": forms.TextInput(attrs={"class": INPUT_CLS}),
            "organization_name": forms.TextInput(attrs={"class": INPUT_CLS}),
            "org_description": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 2}),
            "object_description": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 2}),
            "detailed_description": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 4}),
            "address": forms.TextInput(attrs={"class": INPUT_CLS}),
            "city": forms.TextInput(attrs={"class": INPUT_CLS}),
            "payment_amount": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 0, "step": "0.01"}),
            "max_workers": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 1}),
            "preferred_religion": forms.TextInput(attrs={"class": INPUT_CLS}),
            "date_time": forms.DateTimeInput(attrs={"class": INPUT_CLS, "type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # job_skills — составной PK: начальный набор через through-модель
            self.fields["skills"].initial = list(
                JobSkill.objects.filter(job=self.instance).values_list("skill_id", flat=True)
            )


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": INPUT_CLS, "autofocus": True}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput(attrs={"class": INPUT_CLS}))
