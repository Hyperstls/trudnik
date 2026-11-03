"""Support/feedback form (J144)."""
from django import forms

from .forms_auth import INPUT_CLS

TOPICS = (
    ("question", "Вопрос"),
    ("problem", "Проблема"),
    ("idea", "Идея"),
    ("complaint", "Жалоба"),
)


class SupportForm(forms.Form):
    name = forms.CharField(label="Как к вам обращаться", max_length=150, required=False,
                           widget=forms.TextInput(attrs={"class": INPUT_CLS, "autocomplete": "name"}))
    email = forms.EmailField(label="Email для ответа", max_length=254,
                             widget=forms.EmailInput(attrs={"class": INPUT_CLS, "autocomplete": "email"}))
    topic = forms.ChoiceField(label="Тема", choices=TOPICS,
                              widget=forms.Select(attrs={"class": INPUT_CLS}))
    message = forms.CharField(
        label="Сообщение", min_length=10, max_length=4000,
        widget=forms.Textarea(attrs={"class": INPUT_CLS, "rows": 6}),
    )
