from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid
from datetime import timedelta

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
    telephone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Téléphone')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='CLIENT')
    date_joined = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

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
    client_nom = models.CharField(max_length=100, default='')
    client_prenom = models.CharField(max_length=100, default='')
    date_jour = models.DateField(default=timezone.now)
    nombre_heures = models.PositiveIntegerField(default=1)
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coach = models.ForeignKey(
        'Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'categorie': 'COACH'},
        verbose_name='Coach'
    )

    def __str__(self):
        return f"{self.client_prenom} {self.client_nom} - {self.date_jour} ({self.nombre_heures}h) - {self.montant_paye} FCFA"


class Reservation(models.Model):
    TYPE_CHOICES = [
        ('SEANCE', 'Séance'),
        ('ABONNEMENT', 'Abonnement'),
    ]
    
    STATUT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('CONFIRMEE', 'Confirmée'),
        ('ANNULEE', 'Annulée'),
        ('TERMINEE', 'Terminée'),
    ]
    
    nom_client = models.CharField(max_length=255, verbose_name='Nom du client')
    type_reservation = models.CharField(
        max_length=20, 
        choices=TYPE_CHOICES,
        verbose_name='Type de réservation'
    )
    montant = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        verbose_name='Montant'
    )
    montant_paye = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0,
        verbose_name='Montant payé'
    )
    statut = models.CharField(
        max_length=20, 
        choices=STATUT_CHOICES, 
        default='EN_ATTENTE',
        verbose_name='Statut'
    )
    description = models.TextField(
        blank=True, 
        null=True,
        verbose_name='Description'
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de modification')

    def __str__(self):
        return f"{self.nom_client} - {self.get_type_reservation_display()} - {self.montant} FCFA"

    class Meta:
        verbose_name = 'Réservation'
        verbose_name_plural = 'Réservations'


class Paiement(models.Model):
    client = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': 'CLIENT'}, 
        null=True, 
        blank=True
    )
    abonnement = models.ForeignKey(Abonnement, on_delete=models.SET_NULL, null=True, blank=True)
    seance = models.ForeignKey(Seance, on_delete=models.SET_NULL, null=True, blank=True)
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('EN_ATTENTE', 'En attente'), ('PAYE', 'Payé'), ('ECHEC', 'Échec')], default='EN_ATTENTE')
    mode_paiement = models.CharField(max_length=20, choices=[('ESPECE', 'Espèce'), ('CARTE', 'Carte'), ('CHEQUE', 'Chèque')], default='ESPECE')

    def __str__(self):
        return f"{self.client} - {self.montant} FCFA - {self.status}"


class Ticket(models.Model):
    """Remplace Facture - maintenant utilisé comme ticket de paiement"""
    paiement = models.OneToOneField(Paiement, on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_generation = models.DateTimeField(auto_now_add=True)
    fichier_pdf = models.FileField(upload_to='tickets/')
    type_ticket = models.CharField(max_length=20, choices=[('ABONNEMENT', 'Abonnement'), ('SEANCE', 'Séance')])

    def __str__(self):
        return f"Ticket #{self.uuid} - {self.type_ticket}"


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


class AbonnementClient(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'CLIENT'})
    abonnement = models.ForeignKey(Abonnement, on_delete=models.CASCADE)
    date_debut = models.DateField(default=timezone.now)
    date_fin = models.DateField()
    actif = models.BooleanField(default=True)
    paiement = models.OneToOneField(Paiement, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.client} - {self.abonnement} ({self.date_debut} - {self.date_fin})"


class AbonnementClientPresentiel(models.Model):
    """Modèle pour gérer les abonnements clients en présentiel avec paiement en plusieurs tranches"""
    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
        ('EXPIRE', 'Expiré'),
    ]
    
    STATUT_PAIEMENT_CHOICES = [
        ('PAIEMENT_INACHEVE', 'Paiement inachevé'),
        ('PAIEMENT_TERMINE', 'Paiement terminé'),
    ]
    
    # Informations client (peut être un client existant ou nouveau)
    client = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'CLIENT'}, null=True, blank=True, related_name='abonnements_presentiels')
    client_nom = models.CharField(max_length=100)  # Pour les clients non enregistrés
    client_prenom = models.CharField(max_length=100)  # Pour les clients non enregistrés
    
    # Informations abonnement
    abonnement = models.ForeignKey(Abonnement, on_delete=models.CASCADE)
    date_debut = models.DateField(default=timezone.now)
    date_fin = models.DateField()
    
    # Gestion du paiement
    montant_total = models.DecimalField(max_digits=10, decimal_places=2)  # Montant total de l'abonnement
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Montant déjà payé
    statut_paiement = models.CharField(max_length=20, choices=STATUT_PAIEMENT_CHOICES, default='PAIEMENT_INACHEVE')
    
    # Statut de l'abonnement
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_COURS')
    
    # Informations de création
    date_creation = models.DateTimeField(auto_now_add=True)
    employe_creation = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'EMPLOYE'}, related_name='abonnements_crees')
    
    # Facture générée
    facture_pdf = models.FileField(upload_to='factures/', null=True, blank=True)
    
    def __str__(self):
        nom_client = f"{self.client_prenom} {self.client_nom}" if self.client_prenom and self.client_nom else str(self.client)
        return f"{nom_client} - {self.abonnement.nom} ({self.date_debut} - {self.date_fin})"
    
    def save(self, *args, **kwargs):
        # Calculer automatiquement la date de fin
        if self.abonnement and self.date_debut:
            self.date_fin = self.date_debut + timedelta(days=self.abonnement.duree_jours)
        
        # Mettre à jour le montant total si l'abonnement change
        if self.abonnement:
            self.montant_total = self.abonnement.prix
        
        # Mettre à jour le statut de paiement
        if self.montant_paye >= self.montant_total:
            self.statut_paiement = 'PAIEMENT_TERMINE'
        else:
            self.statut_paiement = 'PAIEMENT_INACHEVE'
        
        # Mettre à jour le statut de l'abonnement
        if self.date_fin and self.date_fin < timezone.now().date():
            self.statut = 'EXPIRE'
        elif self.statut_paiement == 'PAIEMENT_TERMINE':
            self.statut = 'EN_COURS'
        
        super().save(*args, **kwargs)


class HistoriquePaiement(models.Model):
    """Modèle pour tracer l'historique des paiements d'un abonnement présentiel"""
    abonnement_presentiel = models.ForeignKey(AbonnementClientPresentiel, on_delete=models.CASCADE, related_name='historique_paiements')
    montant_ajoute = models.DecimalField(max_digits=10, decimal_places=2)  # Montant ajouté lors de cette modification
    montant_total_apres = models.DecimalField(max_digits=10, decimal_places=2)  # Montant total payé après cette modification
    date_modification = models.DateTimeField(auto_now_add=True)
    employe = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'EMPLOYE'}, related_name='modifications_paiements')
    
    def __str__(self):
        return f"Paiement {self.montant_ajoute} FCFA - {self.date_modification.strftime('%d/%m/%Y %H:%M')}"


class PaiementTranche(models.Model):
    """Modèle pour gérer les paiements en plusieurs tranches pour les abonnements présentiels"""
    abonnement_presentiel = models.ForeignKey(AbonnementClientPresentiel, on_delete=models.CASCADE, related_name='paiements_tranches')
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(auto_now_add=True)
    mode_paiement = models.CharField(max_length=20, choices=[('ESPECE', 'Espèce'), ('CARTE', 'Carte'), ('CHEQUE', 'Chèque')], default='ESPECE')
    employe = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'EMPLOYE'}, related_name='paiements_tranches_effectues')
    
    def __str__(self):
        return f"Tranche {self.id} - {self.montant} FCFA - {self.date_paiement.strftime('%d/%m/%Y')}"
    
    def save(self, *args, **kwargs):
        # Mettre à jour le montant payé de l'abonnement
        if not self.pk:  # Nouveau paiement
            self.abonnement_presentiel.montant_paye += self.montant
            self.abonnement_presentiel.save()
        super().save(*args, **kwargs)


class Facture(models.Model):
    paiement = models.OneToOneField('Paiement', on_delete=models.CASCADE, related_name='facture')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_generation = models.DateTimeField(auto_now_add=True)
    fichier_pdf = models.FileField(upload_to='factures/')
    seance = models.ForeignKey('Seance', on_delete=models.SET_NULL, null=True, blank=True, related_name='factures')
    abonnement = models.ForeignKey('AbonnementClient', on_delete=models.SET_NULL, null=True, blank=True, related_name='factures')
    reservation = models.ForeignKey('Reservation', on_delete=models.SET_NULL, null=True, blank=True, related_name='factures')

    def __str__(self):
        return f"Facture #{self.uuid} - Paiement: {self.paiement.id}"
