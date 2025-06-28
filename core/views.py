from uuid import uuid4
import time
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django.db import transaction

from rest_framework import viewsets, filters, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
#from cinetpay import Order  # SUPPRIMER
from rest_framework.decorators import action

from .models import (
    User, Abonnement, Seance,
    Reservation, Paiement, Ticket,
    Charge, PresencePersonnel, Personnel,
    AbonnementClient
)
from .serializers import (
    UserRegisterSerializer, UserSerializer,
    AbonnementSerializer, SeanceSerializer,
    ReservationSerializer, PaiementSerializer,
    #FactureSerializer,  # SUPPRIMER
    ChargeSerializer,
    PresencePersonnelSerializer, PersonnelSerializer,
    TicketSerializer,
    AbonnementClientSerializer,
    MyTokenObtainPairSerializer
)
from .permissions import IsAdmin, IsEmploye, IsClient, IsAdminOrEmploye, IsClientOrEmploye
# from .cinetpay_client import cinetpay_client  # SUPPRIMER
from django.utils import timezone
from .utils import generer_facture_pdf
from rest_framework_simplejwt.views import TokenObtainPairView

# ---------- Rapports Financiers ----------
class FinancialReportView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        # Période (par défaut: 12 derniers mois)
        months = int(request.query_params.get('months', 12))
        start_date = datetime.now() - timedelta(days=30 * months)
        
        # Revenus totaux (paiements avec statut PAYE)
        total_revenue = Paiement.objects.filter(
            status='PAYE'
        ).aggregate(total=Sum('montant'))['total'] or 0
        
        # Dépenses totales
        total_expenses = Charge.objects.aggregate(
            total=Sum('montant')
        )['total'] or 0
        
        # Profit
        profit = total_revenue - total_expenses
        
        # Revenus mensuels
        monthly_revenue = Paiement.objects.filter(
            status='PAYE',
            date_paiement__gte=start_date
        ).annotate(
            month=TruncMonth('date_paiement')
        ).values('month').annotate(
            total=Sum('montant')
        ).order_by('month')
        
        # Dépenses mensuelles
        monthly_expenses = Charge.objects.filter(
            date__gte=start_date
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total=Sum('montant')
        ).order_by('month')
        
        # Statistiques des abonnements
        subscription_stats = Paiement.objects.filter(
            status='PAYE',
            abonnement__isnull=False
        ).values(
            'abonnement__nom'
        ).annotate(
            count=Count('id'),
            total=Sum('montant')
        ).order_by('-total')
        
        # Statistiques des séances
        session_stats = Paiement.objects.filter(
            status='PAYE',
            seance__isnull=False
        ).values(
            'seance__titre'
        ).annotate(
            count=Count('id'),
            total=Sum('montant')
        ).order_by('-total')
        
        # Nombre de clients actifs (ayant effectué un paiement dans la période)
        active_clients = Paiement.objects.filter(
            status='PAYE',
            date_paiement__gte=start_date
        ).values('client').distinct().count()
        
        return Response({
            'summary': {
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'profit': profit,
                'active_clients': active_clients
            },
            'monthly': {
                'revenue': monthly_revenue,
                'expenses': monthly_expenses
            },
            'subscriptions': subscription_stats,
            'sessions': session_stats
        })


# ---------- Auth ----------
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegisterSerializer


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # On ne renvoie que les champs simples du user
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# ---------- Gestion des Paiements ----------
class ValiderPaiementView(APIView):
    """Permet à un employé de valider un paiement en attente"""
    permission_classes = [IsEmploye]

    def post(self, request, paiement_id):
        try:
            paiement = Paiement.objects.get(id=paiement_id, status='EN_ATTENTE')
            paiement.status = 'PAYE'
            paiement.save()
            
            return Response({
                "message": "Paiement validé avec succès",
                "paiement_id": paiement.id
            })
        except Paiement.DoesNotExist:
            return Response(
                {"error": "Paiement introuvable ou déjà payé"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class PaiementDirectView(APIView):
    """Permet à un employé d'enregistrer un paiement direct à la salle"""
    permission_classes = [IsEmploye]

    def post(self, request):
        client_id = request.data.get('client_id')
        montant = request.data.get('montant')
        mode_paiement = request.data.get('mode_paiement', 'ESPECE')
        abonnement_id = request.data.get('abonnement_id')
        seance_id = request.data.get('seance_id')
        
        if not client_id or not montant:
            return Response(
                {"error": "client_id et montant sont requis"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            client = User.objects.get(id=client_id, role='CLIENT')
        except User.DoesNotExist:
            return Response(
                {"error": "Client introuvable"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Créer le paiement directement payé
        paiement = Paiement.objects.create(
            client=client,
            montant=montant,
            mode_paiement=mode_paiement,
            status='PAYE',
            abonnement_id=abonnement_id,
            seance_id=seance_id
        )

        return Response({
            "message": "Paiement enregistré avec succès",
            "paiement_id": paiement.id
        })


class AbonnementDirectView(APIView):
    """Permet à un employé d'enregistrer un abonnement direct à la salle"""
    permission_classes = [IsEmploye]

    def post(self, request):
        client_id = request.data.get('client_id')
        abonnement_id = request.data.get('abonnement_id')
        mode_paiement = request.data.get('mode_paiement', 'ESPECE')
        
        if not client_id or not abonnement_id:
            return Response(
                {"error": "client_id et abonnement_id sont requis"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            client = User.objects.get(id=client_id, role='CLIENT')
            abonnement = Abonnement.objects.get(id=abonnement_id)
        except (User.DoesNotExist, Abonnement.DoesNotExist):
            return Response(
                {"error": "Client ou abonnement introuvable"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Créer le paiement directement payé
        paiement = Paiement.objects.create(
            client=client,
            abonnement=abonnement,
            montant=abonnement.prix,
            mode_paiement=mode_paiement,
            status='PAYE'
        )
        
        # Remplace la création du ticket par get_or_create pour éviter l'erreur d'unicité
        pdf_file = generer_facture_pdf(paiement, paiement.abonnement, type_ticket='ABONNEMENT')
        ticket, created = Ticket.objects.get_or_create(
            paiement=paiement,
            defaults={
                'fichier_pdf': pdf_file,
                'type_ticket': 'ABONNEMENT'
            }
        )
        
        return Response({
            "message": "Abonnement enregistré avec succès",
            "paiement_id": paiement.id,
            "montant": abonnement.prix
        })


# ---------- CRUD Métiers ----------
class AbonnementViewSet(viewsets.ModelViewSet):
    queryset = Abonnement.objects.all()
    serializer_class = AbonnementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nom']

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdminOrEmploye()]
        elif self.action == 'list':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def clients(self, request, pk=None):
        abonnement = self.get_object()
        # On suppose que chaque client a un Paiement PAYE pour cet abonnement
        paiements = abonnement.paiement_set.filter(status='PAYE').select_related('client')
        clients = []
        for paiement in paiements:
            client = paiement.client
            # Calcul du nombre de jours restants (exemple: date_paiement + duree_jours)
            if abonnement.duree_jours:
                date_fin = paiement.date_paiement + timedelta(days=abonnement.duree_jours)
                jours_restants = (date_fin - datetime.now()).days
            else:
                jours_restants = None
            clients.append({
                'id': client.id,
                'email': client.email,
                'nom': client.nom,
                'prenom': client.prenom,
                'date_paiement': paiement.date_paiement,
                'date_fin': date_fin if abonnement.duree_jours else None,
                'jours_restants': jours_restants,
                'montant': paiement.montant,
            })
        return Response(clients)


class SeanceViewSet(viewsets.ModelViewSet):
    queryset = Seance.objects.all()
    serializer_class = SeanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['titre']

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdminOrEmploye()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        print("=== DEBUG SEANCE CREATE ===")
        print("Request data:", request.data)
        print("Request user:", request.user)
        response = super().create(request, *args, **kwargs)
        print("Response data:", response.data)
        return response

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def coachs(self, request):
        """Récupérer la liste des coachs du personnel"""
        coachs = Personnel.objects.filter(categorie='COACH')
        serializer = PersonnelSerializer(coachs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def participants(self, request, pk=None):
        seance = self.get_object()
        # On suppose que chaque client a une réservation CONFIRMEE pour cette séance
        reservations = seance.reservation_set.filter(statut='CONFIRMEE').select_related('client')
        participants = []
        for reservation in reservations:
            client = reservation.client
            participants.append({
                'id': client.id,
                'email': client.email,
                'nom': client.nom,
                'prenom': client.prenom,
                'telephone': client.telephone,
                'date_reservation': reservation.date_reservation,
            })
        return Response(participants)


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'seance', 'statut']

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsClientOrEmploye()]
        return [IsClientOrEmploye()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            return Reservation.objects.filter(client=user)
        elif user.is_authenticated and user.role == 'EMPLOYE':
            return Reservation.objects.all()
        return Reservation.objects.none()

    def perform_create(self, serializer):
        reservation = serializer.save(client=self.request.user)
        
        # Calculer le montant selon le nombre d'heures (tarif par heure)
        tarif_par_heure = 5000  # 5000 FCFA par heure
        montant_calcule = reservation.nombre_heures * tarif_par_heure
        reservation.montant_calcule = montant_calcule
        reservation.save()
        
        # Créer automatiquement un paiement en attente pour cette réservation
        paiement = Paiement.objects.create(
            client=self.request.user,
            reservation=reservation,
            montant=montant_calcule,
            mode_paiement='ESPECE',
            status='EN_ATTENTE'
        )
        
        # Générer le ticket PDF (billet de réservation)
        pdf_file = generer_facture_pdf(reservation, paiement, type_ticket='SEANCE')
        Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='SEANCE'
        )


class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.all()
    serializer_class = PaiementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'abonnement', 'seance', 'status']

    def get_permissions(self):
        return [IsClientOrEmploye()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            return Paiement.objects.filter(client=user)
        elif user.is_authenticated and user.role == 'EMPLOYE':
            return Paiement.objects.all()
        return Paiement.objects.none()


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ticket.objects.all()
    # Il faudra créer TicketSerializer
    serializer_class = TicketSerializer

    def get_permissions(self):
        return [IsClient()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            return Ticket.objects.filter(paiement__client=user)
        return Ticket.objects.none()


class ChargeViewSet(viewsets.ModelViewSet):
    queryset = Charge.objects.all()
    serializer_class = ChargeSerializer

    def get_permissions(self):
        return [IsAdminOrEmploye()]


class PersonnelViewSet(viewsets.ModelViewSet):
    queryset = Personnel.objects.all()
    serializer_class = PersonnelSerializer
    permission_classes = [IsAdminOrEmploye]


class PresencePersonnelViewSet(viewsets.ModelViewSet):
    queryset = PresencePersonnel.objects.all()
    serializer_class = PresencePersonnelSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['personnel', 'date_jour', 'statut']

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsEmploye()]
        return [IsAdminOrEmploye()]

    @action(detail=False, methods=['get'], permission_classes=[IsAdmin])
    def rapport_journalier(self, request):
        from datetime import date
        today = date.today()
        presences = PresencePersonnel.objects.filter(date_jour=today)
        serializer = self.get_serializer(presences, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        print("=== DEBUG PERFORM CREATE ===")
        print("Request data:", self.request.data)
        print("Validated data:", serializer.validated_data)
        print("User:", self.request.user)
        
        # Le serializer gère maintenant tout automatiquement
        # On sauvegarde simplement
        serializer.save()

class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrEmploye]

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

class SeanceDirecteView(APIView):
    permission_classes = [IsEmploye]

    def post(self, request):
        data = request.data
        client_id = data.get('client_id')
        seance = Seance.objects.create(
            date_jour=data['date_jour'],
            client_nom=data.get('client_nom', ''),
            client_prenom=data.get('client_prenom', ''),
            nombre_heures=data['nombre_heures'],
            montant_paye=data['montant_paye'],
        )
        paiement = Paiement.objects.create(
            client_id=client_id if client_id else None,
            seance=seance,
            montant=data['montant_paye'],
            status='PAYE',
            mode_paiement='ESPECE'
        )
        pdf_file = generer_facture_pdf(seance, paiement, type_ticket='SEANCE')
        ticket = Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='SEANCE'
        )
        response_data = SeanceSerializer(seance, context={'request': request}).data
        response_data['ticket_id'] = ticket.id
        response_data['ticket_pdf_url'] = ticket.fichier_pdf.url if ticket.fichier_pdf else None
        return Response(response_data, status=status.HTTP_201_CREATED)

class AbonnementClientDirectView(APIView):
    permission_classes = [IsEmploye]

    def post(self, request):
        data = request.data
        client_id = data['client_id']
        abonnement_id = data['abonnement_id']
        date_debut_str = data.get('date_debut', timezone.now().date())
        if isinstance(date_debut_str, str):
            date_debut = datetime.strptime(date_debut_str, "%Y-%m-%d").date()
        else:
            date_debut = date_debut_str
        abonnement = Abonnement.objects.get(id=abonnement_id)
        date_fin = date_debut + timedelta(days=abonnement.duree_jours)
        paiement = Paiement.objects.create(
            client_id=client_id,
            abonnement_id=abonnement_id,
            montant=abonnement.prix,
            status='PAYE',
            mode_paiement='ESPECE'
        )
        ab_client = AbonnementClient.objects.create(
            client_id=client_id,
            abonnement_id=abonnement_id,
            date_debut=date_debut,
            date_fin=date_fin,
            actif=True,
            paiement=paiement
        )
        pdf_file = generer_facture_pdf(ab_client, paiement, type_ticket='ABONNEMENT')
        ticket, created = Ticket.objects.get_or_create(
            paiement=paiement,
            defaults={
                'fichier_pdf': pdf_file,
                'type_ticket': 'ABONNEMENT'
            }
        )
        response_data = AbonnementClientSerializer(ab_client).data
        response_data['ticket_id'] = ticket.id
        response_data['ticket_pdf_url'] = ticket.fichier_pdf.url if ticket.fichier_pdf else None
        return Response(response_data, status=status.HTTP_201_CREATED)

class ValiderReservationSeanceView(APIView):
    permission_classes = [IsEmploye]

    def post(self, request, reservation_id):
        try:
            reservation = Reservation.objects.get(id=reservation_id, statut='EN_ATTENTE')
        except Reservation.DoesNotExist:
            return Response({'error': 'Réservation introuvable ou déjà validée'}, status=404)
        reservation.statut = 'CONFIRMEE'
        reservation.paye = True
        reservation.save()
        paiement = Paiement.objects.create(
            client=reservation.client,
            seance=reservation.seance,
            montant=reservation.seance.montant_paye or 0,
            status='PAYE',
            mode_paiement='ESPECE',
            reservation=reservation
        )
        pdf_file = generer_facture_pdf(reservation.seance, paiement, type_ticket='SEANCE')
        ticket = Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='SEANCE'
        )
        return Response({'message': 'Réservation validée et facture générée.', 'ticket_id': ticket.id, 'ticket_pdf_url': ticket.fichier_pdf.url if ticket.fichier_pdf else None})

class ValiderReservationAbonnementView(APIView):
    permission_classes = [IsEmploye]

    def post(self, request, ab_client_id):
        try:
            ab_client = AbonnementClient.objects.get(id=ab_client_id, actif=False)
        except AbonnementClient.DoesNotExist:
            return Response({'error': 'Abonnement client introuvable ou déjà validé'}, status=404)
        ab_client.actif = True
        ab_client.save()
        paiement = Paiement.objects.create(
            client=ab_client.client,
            abonnement=ab_client.abonnement,
            montant=ab_client.abonnement.prix,
            status='PAYE',
            mode_paiement='ESPECE'
        )
        ab_client.paiement = paiement
        ab_client.save()
        pdf_file = generer_facture_pdf(ab_client, paiement, type_ticket='ABONNEMENT')
        ticket = Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='ABONNEMENT'
        )
        return Response({'message': 'Abonnement validé et facture générée.', 'ticket_id': ticket.id, 'ticket_pdf_url': ticket.fichier_pdf.url if ticket.fichier_pdf else None})

class AbonnementClientReservationView(APIView):
    permission_classes = [IsClient]

    def post(self, request):
        data = request.data
        abonnement_id = data['abonnement_id']
        date_debut = data.get('date_debut', timezone.now().date())
        abonnement = Abonnement.objects.get(id=abonnement_id)
        date_fin = date_debut + timedelta(days=abonnement.duree_jours)
        ab_client = AbonnementClient.objects.create(
            client=request.user,
            abonnement_id=abonnement_id,
            date_debut=date_debut,
            date_fin=date_fin,
            actif=False
        )
        paiement = Paiement.objects.create(
            client=request.user,
            abonnement_id=abonnement_id,
            montant=abonnement.prix,
            status='EN_ATTENTE',
            mode_paiement='ESPECE'
        )
        # Générer le ticket PDF (billet de réservation)
        pdf_file = generer_facture_pdf(ab_client, paiement, type_ticket='ABONNEMENT')
        Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='ABONNEMENT'
        )
        return Response({'message': 'Réservation d\'abonnement enregistrée, ticket généré.'}, status=status.HTTP_201_CREATED)

class AbonnementClientViewSet(viewsets.ModelViewSet):
    queryset = AbonnementClient.objects.all()
    serializer_class = AbonnementClientSerializer
    permission_classes = [IsAdminOrEmploye]

class LoginView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    permission_classes = []
