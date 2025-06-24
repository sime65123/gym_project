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
from cinetpay import Order
from rest_framework.decorators import action

from .models import (
    User, Abonnement, Seance,
    Reservation, Paiement, Facture,
    Charge, PresencePersonnel, Personnel
)
from .serializers import (
    UserRegisterSerializer, UserSerializer,
    AbonnementSerializer, SeanceSerializer,
    ReservationSerializer, PaiementSerializer,
    FactureSerializer, ChargeSerializer,
    PresencePersonnelSerializer, PersonnelSerializer
)
from .permissions import IsAdmin, IsEmploye, IsClient, IsAdminOrEmploye, IsClientOrEmploye
from .cinetpay_client import cinetpay_client
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


# ---------- Recharge Compte ----------
class RechargeCompteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        montant = request.data.get('montant')
        if not montant:
            return Response({"error": "Montant requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            montant = float(montant)
            if montant <= 0:
                return Response({"error": "Le montant doit être positif"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": "Montant invalide"}, status=status.HTTP_400_BAD_REQUEST)

        transaction_id = f"recharge-{request.user.id}-{uuid4().hex[:8]}"

        # Créer un paiement pour la recharge
        paiement = Paiement.objects.create(
            client=request.user,
            montant=montant,
            mode_paiement='CINETPAY',
            status='EN_ATTENTE',
            transaction_id=transaction_id
        )

        order = Order(
            transaction_id=transaction_id,
            amount=montant,
            currency=settings.CINETPAY_CURRENCY,
            description=f"Recharge compte GYM ZONE {transaction_id}",
            notify_url=settings.CINETPAY_NOTIFY_URL,
            return_url=settings.CINETPAY_RETURN_URL,
            customer_name=request.user.nom,
            customer_surname=request.user.prenom,
            customer_phone_number=request.user.telephone,
            customer_email=request.user.email,
        )

        response = cinetpay_client.initialize_transaction(order)

        return Response({
            "paiement_id": paiement.id,
            "transaction_id": transaction_id,
            "cinetpay_response": response.json
        }, status=response.status_code)

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



# ---------- Paiement Init ----------
class PaiementInitAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        montant = request.data.get('montant')
        if not montant:
            return Response({"error": "Montant requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            montant = float(montant)
            if montant <= 0:
                return Response({"error": "Le montant doit être positif"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": "Montant invalide"}, status=status.HTTP_400_BAD_REQUEST)

        abonnement_id = request.data.get('abonnement')
        seance_id = request.data.get('seance')
        use_balance = request.data.get('use_balance', False)

        # Vérification d'existence si fourni
        if abonnement_id:
            if not Abonnement.objects.filter(id=abonnement_id).exists():
                return Response({"error": f"Abonnement {abonnement_id} introuvable"}, status=status.HTTP_400_BAD_REQUEST)
        if seance_id:
            if not Seance.objects.filter(id=seance_id).exists():
                return Response({"error": f"Séance {seance_id} introuvable"}, status=status.HTTP_400_BAD_REQUEST)

        # Si l'utilisateur veut utiliser son solde
        if use_balance:
            # Vérifier si le solde est suffisant
            if request.user.solde < montant:
                return Response({
                    "error": "Solde insuffisant",
                    "solde": request.user.solde,
                    "montant": montant
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Utiliser une transaction pour garantir l'atomicité
            with transaction.atomic():
                # Créer un paiement directement payé
                paiement = Paiement.objects.create(
                    client=request.user,
                    montant=montant,
                    abonnement_id=abonnement_id or None,
                    seance_id=seance_id or None,
                    mode_paiement='SOLDE',
                    status='PAYE',
                    transaction_id=f"solde-{request.user.id}-{uuid4().hex[:8]}"
                )
                
                # Déduire le montant du solde de l'utilisateur
                request.user.solde = F('solde') - montant
                request.user.save(update_fields=['solde'])
            
            return Response({
                "paiement_id": paiement.id,
                "status": "PAYE",
                "message": "Paiement effectué avec succès via le solde du compte"
            })
        else:
            # Paiement via CinetPay
            transaction_id = f"{request.user.id}-{uuid4().hex[:8]}"

            paiement = Paiement.objects.create(
                client=request.user,
                montant=montant,
                abonnement_id=abonnement_id or None,
                seance_id=seance_id or None,
                mode_paiement='CINETPAY',
                status='EN_ATTENTE',
                transaction_id=transaction_id
            )

            order = Order(
                transaction_id=transaction_id,
                amount=montant,
                currency=settings.CINETPAY_CURRENCY,
                description=f"Paiement GYM ZONE {transaction_id}",
                notify_url=settings.CINETPAY_NOTIFY_URL,
                return_url=settings.CINETPAY_RETURN_URL,
                customer_name=request.user.nom,
                customer_surname=request.user.prenom,
                customer_phone_number=request.user.telephone,
                customer_email=request.user.email,
            )

            response = cinetpay_client.initialize_transaction(order)

            return Response({
                "paiement_id": paiement.id,
                "transaction_id": transaction_id,
                "cinetpay_response": response.json
            }, status=response.status_code)


# ---------- Webhook ----------
class CinetPayWebhook(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        tx_id = request.data.get('cpm_trans_id')
        if not tx_id:
            return Response({"error": "transaction manquant"}, status=status.HTTP_400_BAD_REQUEST)
        resp = cinetpay_client.get_transaction(tx_id)
        data = resp.json

        paiement = Paiement.objects.filter(transaction_id=tx_id).first()
        if not paiement:
            return Response({"error": "paiement introuvable"}, status=status.HTTP_400_BAD_REQUEST)

        # Utiliser une transaction pour garantir l'atomicité
        with transaction.atomic():
            if data.get('cpm_result') == '00':
                paiement.status = 'PAYE'
                
                # Si c'est une recharge de compte (vérifier le préfixe du transaction_id)
                if tx_id.startswith('recharge-'):
                    # Mettre à jour le solde de l'utilisateur
                    user = paiement.client
                    user.solde = F('solde') + paiement.montant
                    user.save(update_fields=['solde'])
            else:
                paiement.status = 'ECHEC'
            
            paiement.save()
        
        return Response({"message": "OK"})


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
                'telephone': client.telephone,
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
        serializer.save(client=self.request.user)


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


class FactureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Facture.objects.all()
    serializer_class = FactureSerializer

    def get_permissions(self):
        return [IsClient()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            return Facture.objects.filter(paiement__client=user)
        return Facture.objects.none()


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
    permission_classes = [IsAdmin]

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
