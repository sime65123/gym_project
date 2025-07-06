from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Abonnement, Seance, Reservation,
    Paiement, Ticket, Charge, PresencePersonnel, Personnel
)

class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'nom', 'prenom', 'role', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informations personnelles', {'fields': ('nom', 'prenom')}),
        ('Rôle et permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
        ('Dates', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'prenom', 'role', 'password1', 'password2'),
        }),
    )

class AbonnementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix', 'duree_jours', 'actif')
    search_fields = ('nom',)
    list_filter = ('actif',)

class SeanceAdmin(admin.ModelAdmin):
    list_display = ('client_nom', 'client_prenom', 'date_jour', 'nombre_heures', 'montant_paye', 'coach')
    search_fields = ('client_nom', 'client_prenom', 'coach')
    list_filter = ('date_jour', 'coach')

class ReservationAdmin(admin.ModelAdmin):
    list_display = ('nom_client', 'type_reservation', 'montant', 'statut')
    search_fields = ('nom_client', 'description')
    list_filter = ('type_reservation', 'statut')
    fields = ('nom_client', 'type_reservation', 'montant', 'statut', 'description')
    
    def save_model(self, request, obj, form, change):
        if not change:
            # Logique à exécuter lors de la création d'une nouvelle réservation
            pass
        super().save_model(request, obj, form, change)

class PaiementAdmin(admin.ModelAdmin):
    list_display = ('client', 'montant', 'date_paiement', 'status', 'mode_paiement')
    search_fields = ('client__nom', 'client__prenom')
    list_filter = ('status', 'mode_paiement', 'date_paiement')

class TicketAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'paiement', 'type_ticket', 'date_generation')
    search_fields = ('uuid', 'paiement__client__nom', 'paiement__client__prenom')
    list_filter = ('type_ticket', 'date_generation')

class ChargeAdmin(admin.ModelAdmin):
    list_display = ('titre', 'montant', 'date')
    search_fields = ('titre',)
    list_filter = ('date',)

class PresencePersonnelAdmin(admin.ModelAdmin):
    list_display = ['personnel', 'date_jour', 'statut', 'heure_arrivee']
    list_filter = ['date_jour', 'statut', 'personnel__categorie']
    search_fields = ['personnel__nom', 'personnel__prenom']
    date_hierarchy = 'date_jour'

admin.site.register(User, UserAdmin)
admin.site.register(Abonnement, AbonnementAdmin)
admin.site.register(Seance, SeanceAdmin)
admin.site.register(Reservation, ReservationAdmin)
admin.site.register(Paiement, PaiementAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(Charge, ChargeAdmin)
admin.site.register(PresencePersonnel, PresencePersonnelAdmin)
admin.site.register(Personnel)
