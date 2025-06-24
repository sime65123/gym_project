from django.core.management.base import BaseCommand
from core.models import Seance, Personnel

class Command(BaseCommand):
    help = 'Corrige les coachs des séances existantes'

    def handle(self, *args, **options):
        # Récupérer toutes les séances
        seances = Seance.objects.all()
        
        # Récupérer le premier coach disponible
        coachs = Personnel.objects.filter(categorie='COACH')
        
        if not coachs.exists():
            self.stdout.write(
                self.style.WARNING('Aucun coach trouvé dans le personnel. Créez d\'abord des coachs.')
            )
            return
        
        # Utiliser le premier coach disponible
        default_coach = coachs.first()
        
        # Corriger les séances sans coach
        seances_sans_coach = seances.filter(coach__isnull=True)
        
        if seances_sans_coach.exists():
            seances_sans_coach.update(coach=default_coach)
            self.stdout.write(
                self.style.SUCCESS(f'{seances_sans_coach.count()} séances ont été mises à jour avec le coach par défaut.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Toutes les séances ont déjà un coach assigné.')
            )
        
        # Afficher le statut final
        for seance in seances:
            coach_info = f"{seance.coach.prenom} {seance.coach.nom}" if seance.coach else "Aucun coach"
            self.stdout.write(f"Séance '{seance.titre}': {coach_info}") 