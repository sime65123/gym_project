from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role="CLIENT", **extra_fields):
        if not email:
            raise ValueError('Email est requis')
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('ADMIN', 'Administrateur'),
        ('EMPLOYE', 'Employé'),
        ('CLIENT', 'Client'),
    ]

    email = models.EmailField(unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='CLIENT')
    date_joined = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    solde = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']

    objects = UserManager()

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.role})"


class Abonnement(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    duree_jours = models.PositiveIntegerField()
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.nom


class Personnel(models.Model):
    CATEGORIES = [
        ("COACH", "Coach"),
        ("MENAGE", "Ménage"),
        ("AIDE_SOIGNANT", "Aide-soignant"),
        ("AUTRE", "Autre"),
    ]
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    date_emploi = models.DateField()
    categorie = models.CharField(max_length=20, choices=CATEGORIES)

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.categorie})"


class Seance(models.Model):
    titre = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    date_heure = models.DateTimeField()
    coach = models.ForeignKey(Personnel, on_delete=models.SET_NULL, null=True, limit_choices_to={'categorie': 'COACH'})
    capacite = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.titre} - {self.date_heure}"


class Reservation(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'CLIENT'})
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE)
    date_reservation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=[('CONFIRMEE', 'Confirmée'), ('ANNULEE', 'Annulée')], default='CONFIRMEE')

    def __str__(self):
        return f"Réservation - {self.client} / {self.seance}"


class Paiement(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'CLIENT'})
    abonnement = models.ForeignKey(Abonnement, on_delete=models.SET_NULL, null=True, blank=True)
    seance = models.ForeignKey(Seance, on_delete=models.SET_NULL, null=True, blank=True)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('EN_ATTENTE', 'En attente'), ('PAYE', 'Payé'), ('ECHEC', 'Échec')], default='EN_ATTENTE')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    mode_paiement = models.CharField(max_length=20, choices=[('CINETPAY', 'CinetPay'), ('ESPECE', 'Espèce')])

    def __str__(self):
        return f"{self.client} - {self.montant} FCFA - {self.status}"


class Facture(models.Model):
    paiement = models.OneToOneField(Paiement, on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_generation = models.DateTimeField(auto_now_add=True)
    fichier_pdf = models.FileField(upload_to='factures/')

    def __str__(self):
        return f"Facture #{self.uuid}"


class Charge(models.Model):
    titre = models.CharField(max_length=100)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    description = models.TextField(blank=True)

    def __str__(self):
        return self.titre


class PresencePersonnel(models.Model):
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, null=True, blank=True)
    employe = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, limit_choices_to={'role': 'EMPLOYE'})
    statut = models.CharField(max_length=10, choices=[("PRESENT", "Présent"), ("ABSENT", "Absent")], default="PRESENT")
    heure_arrivee = models.TimeField(null=True, blank=True)
    date_jour = models.DateField()

    def __str__(self):
        if self.personnel:
            return f"{self.personnel} - {self.date_jour} - {self.statut}"
        elif self.employe:
            return f"{self.employe} - {self.date_jour} - {self.statut}"
        return f"Présence - {self.date_jour} - {self.statut}"
