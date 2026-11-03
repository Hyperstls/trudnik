"""Design-system partials (J139)."""
from django import forms
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class SampleForm(forms.Form):
    name = forms.CharField(label="Имя", required=True)


class UIPartialTests(SimpleTestCase):
    def test_button_link_with_icon(self):
        html = render_to_string("core/_ui_button.html", {
            "label": "Сохранить", "variant": "primary", "href": "/jobs", "icon": "plus",
        })
        self.assertIn('href="/jobs"', html)
        self.assertIn("ui-btn--primary", html)
        self.assertIn("#plus", html)

    def test_button_disabled(self):
        html = render_to_string("core/_ui_button.html", {
            "label": "Нельзя", "disabled": True,
        })
        self.assertIn("disabled", html)
        self.assertIn("ui-btn--primary", html)

    def test_badge_variants(self):
        html = render_to_string("core/_ui_badge.html", {
            "label": "Принят", "variant": "success",
        })
        self.assertIn("ui-badge--success", html)
        self.assertIn("Принят", html)

    def test_field_renders_label_required_and_errors(self):
        form = SampleForm(data={"name": ""})
        self.assertFalse(form.is_valid())
        html = render_to_string("core/_ui_field.html", {
            "field": form["name"], "hint": "Как к вам обращаться",
        })
        self.assertIn("ui-field__label", html)
        self.assertIn("Имя", html)
        self.assertIn("ui-field__required", html)
        self.assertIn("ui-field__hint", html)
        self.assertIn("ui-field__error", html)

    def test_empty_state_uses_button_partial(self):
        html = render_to_string("core/_ui_empty_state.html", {
            "title": "Пусто", "action_url": "/jobs", "action_label": "К заданиям",
        })
        self.assertIn("ui-btn--primary", html)
        self.assertIn("К заданиям", html)
