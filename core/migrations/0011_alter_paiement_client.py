# Generated by Django 5.1.8 on 2025-06-27 01:39

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_remove_seance_capacite_remove_seance_client_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paiement',
            name='client',
            field=models.ForeignKey(blank=True, limit_choices_to={'role': 'CLIENT'}, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]
