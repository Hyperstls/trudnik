# State-only миграция (unmanaged-модели): отражает SQL-миграцию 164 —
# удаление спецкатегории ПДн «вероисповедание» из profiles и jobs (152-ФЗ ст.10).
# В БД колонки убирает migrations/164_drop_religion_columns.sql.
# Profile.religion в state-истории миграций отсутствовала (0001 её не содержал),
# поэтому снимается только Job.preferred_religion; makemigrations --check пуст (R062).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_errorevent'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='preferred_religion',
        ),
    ]
