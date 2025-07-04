# Generated by Django 5.1.8 on 2025-06-22 21:28

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_user_solde'),
    ]

    operations = [
        migrations.CreateModel(
            name='Personnel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('prenom', models.CharField(max_length=100)),
                ('date_emploi', models.DateField()),
                ('categorie', models.CharField(choices=[('COACH', 'Coach'), ('MENAGE', 'Ménage'), ('AIDE_SOIGNANT', 'Aide-soignant'), ('AUTRE', 'Autre')], max_length=20)),
            ],
        ),
        migrations.RenameField(
            model_name='presencepersonnel',
            old_name='date',
            new_name='date_jour',
        ),
        migrations.AlterUniqueTogether(
            name='presencepersonnel',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='presencepersonnel',
            name='heure_arrivee',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='presencepersonnel',
            name='statut',
            field=models.CharField(choices=[('PRESENT', 'Présent'), ('ABSENT', 'Absent')], default='PRESENT', max_length=10),
        ),
        migrations.AddField(
            model_name='presencepersonnel',
            name='personnel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.personnel'),
        ),
        migrations.RemoveField(
            model_name='presencepersonnel',
            name='commentaire',
        ),
        migrations.RemoveField(
            model_name='presencepersonnel',
            name='employe',
        ),
        migrations.RemoveField(
            model_name='presencepersonnel',
            name='present',
        ),
    ]
