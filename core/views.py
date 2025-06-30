from uuid import uuid4
import time
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django.db import transaction

from rest_framework import viewsets, filters, permissions, status, generics, serializers
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
    AbonnementClient, AbonnementClientPresentiel, PaiementTranche, HistoriquePaiement
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
    AbonnementClientPresentielSerializer,
    PaiementTrancheSerializer,
    HistoriquePaiementSerializer,
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
        print("\n=== FinancialReportView.get() appelé ===")
        print(f"Utilisateur: {request.user}")
        print(f"Rôle: {getattr(request.user, 'role', 'Non défini')}")
        print(f"Headers: {request.headers}")
        print(f"Query params: {request.query_params}")

        try:
            # Période (par défaut: 12 derniers mois)
            months = int(request.query_params.get('months', 12))
            start_date = datetime.now() - timedelta(days=30 * months)
            
            print(f"Période analysée: {start_date} à {datetime.now()}")
            
            # Revenus totaux (paiements avec statut PAYE)
            total_revenue = Paiement.objects.filter(
                status='PAYE'
            ).aggregate(total=Sum('montant'))['total'] or 0
            
            print(f"Revenus totaux: {total_revenue}")
            
            # Dépenses totales
            total_expenses = Charge.objects.aggregate(
                total=Sum('montant')
            )['total'] or 0
            
            print(f"Dépenses totales: {total_expenses}")
            
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
            
            print(f"Revenus mensuels: {list(monthly_revenue)}")
            
            # Dépenses mensuelles
            monthly_expenses = Charge.objects.filter(
                date__gte=start_date
            ).annotate(
                month=TruncMonth('date')
            ).values('month').annotate(
                total=Sum('montant')
            ).order_by('month')
            
            print(f"Dépenses mensuelles: {list(monthly_expenses)}")
            
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
            
            print(f"Nombre de clients actifs: {active_clients}")
            
            response_data = {
                'summary': {
                    'total_revenue': total_revenue,
                    'total_expenses': total_expenses,
                    'profit': profit,
                    'active_clients': active_clients
                },
                'monthly': {
                    'revenue': list(monthly_revenue),
                    'expenses': list(monthly_expenses)
                },
                'subscriptions': list(subscription_stats),
                'sessions': list(session_stats)
            }
            
            print("Réponse finale:", response_data)
            
            return Response(response_data)
            
        except Exception as e:
            print(f"Erreur dans FinancialReportView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ---------- Auth ----------
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegisterSerializer


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request):
        """Récupérer les informations du profil de l'utilisateur connecté"""
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    def patch(self, request):
        """Mettre à jour le profil de l'utilisateur connecté"""
        serializer = self.serializer_class(
            request.user, 
            data=request.data, 
            partial=True,
            context={'request': request}  # Ajout du contexte pour le sérialiseur
        )
        
        try:
            if not serializer.is_valid():
                return Response(
                    {'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Sauvegarder les modifications
            user = serializer.save()
            
            # Préparer la réponse
            response_data = self.serializer_class(user).data
            
            # Si un nouveau mot de passe a été fourni, on renvoie un nouveau token
            if 'new_password' in request.data or 'password' in request.data:
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken.for_user(user)
                response_data['tokens'] = {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            
            return Response(response_data)
            
        except serializers.ValidationError as e:
            return Response(
                {'errors': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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


# ---------- Abonnements Clients Présentiels ----------
class AbonnementClientPresentielViewSet(viewsets.ModelViewSet):
    queryset = AbonnementClientPresentiel.objects.all()
    serializer_class = AbonnementClientPresentielSerializer
    permission_classes = [IsAdminOrEmploye]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['client_nom', 'client_prenom', 'abonnement__nom']
    filterset_fields = ['statut', 'statut_paiement', 'abonnement']

    def perform_create(self, serializer):
        # Assigner l'employé qui crée l'abonnement
        serializer.save(employe_creation=self.request.user)

    def perform_update(self, serializer):
        # Vérifier si le montant payé a été modifié
        if self.get_object().montant_paye != serializer.validated_data.get('montant_paye', self.get_object().montant_paye):
            ancien_montant = self.get_object().montant_paye
            nouveau_montant = serializer.validated_data.get('montant_paye', self.get_object().montant_paye)
            montant_ajoute = nouveau_montant - ancien_montant
            
            if montant_ajoute > 0:
                # Créer un historique de paiement
                HistoriquePaiement.objects.create(
                    abonnement_presentiel=self.get_object(),
                    montant_ajoute=montant_ajoute,
                    montant_total_apres=nouveau_montant,
                    employe=self.request.user
                )
        
        serializer.save()

    @action(detail=True, methods=['post'])
    def modifier_montant_paye(self, request, pk=None):
        """Ajouter un montant au paiement et créer automatiquement l'historique"""
        from decimal import Decimal
        import logging
        abonnement = self.get_object()
        montant_ajoute = request.data.get('montant_ajoute')

        if not montant_ajoute:
            return Response(
                {"error": "Le montant à ajouter est requis"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            montant_ajoute = Decimal(str(montant_ajoute))
        except (ValueError, TypeError):
            return Response(
                {"error": "Le montant doit être un nombre valide"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        if montant_ajoute <= 0:
            return Response(
                {"error": "Le montant ajouté doit être supérieur à zéro"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        ancien_montant = abonnement.montant_paye
        nouveau_montant = ancien_montant + montant_ajoute
        if nouveau_montant > abonnement.montant_total:
            return Response(
                {"error": f"Le montant total ne peut pas dépasser {abonnement.montant_total} FCFA"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        # Log pour debug
        logging.warning(f"[DEBUG] Ajout paiement: ancien={ancien_montant}, ajoute={montant_ajoute}, nouveau={nouveau_montant}")
        # Créer un historique de paiement
        HistoriquePaiement.objects.create(
            abonnement_presentiel=abonnement,
            montant_ajoute=montant_ajoute,
            montant_total_apres=nouveau_montant,
            employe=request.user
        )
        # Mettre à jour le montant payé
        abonnement.montant_paye = nouveau_montant
        abonnement.save()

        # Générer la facture automatiquement si paiement terminé et pas encore de facture
        if abonnement.montant_paye >= abonnement.montant_total and not abonnement.facture_pdf:
            from .utils import generer_facture_pdf
            pdf_file = generer_facture_pdf(abonnement, None, type_ticket='ABONNEMENT')
            abonnement.facture_pdf = pdf_file
            abonnement.save()

        return Response({
            "message": "Montant ajouté avec succès",
            "montant_paye": float(nouveau_montant)
        })

    @action(detail=True, methods=['post'])
    def ajouter_paiement(self, request, pk=None):
        """Ajouter un paiement en tranche pour un abonnement présentiel"""
        abonnement = self.get_object()
        montant = request.data.get('montant')
        mode_paiement = request.data.get('mode_paiement', 'ESPECE')
        
        if not montant:
            return Response(
                {"error": "Le montant est requis"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Vérifier que le montant ne dépasse pas le montant restant
        montant_restant = abonnement.montant_total - abonnement.montant_paye
        if montant > montant_restant:
            return Response(
                {"error": f"Le montant ne peut pas dépasser {montant_restant} FCFA"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Créer le paiement en tranche
        paiement_tranche = PaiementTranche.objects.create(
            abonnement_presentiel=abonnement,
            montant=montant,
            mode_paiement=mode_paiement,
            employe=request.user
        )
        
        # Générer la facture si le paiement est complet
        if abonnement.statut_paiement == 'PAIEMENT_TERMINE' and not abonnement.facture_pdf:
            from .utils import generer_facture_pdf
            pdf_file = generer_facture_pdf(abonnement, None, type_ticket='ABONNEMENT')
            abonnement.facture_pdf = pdf_file
            abonnement.save()
        
        return Response({
            "message": "Paiement ajouté avec succès",
            "paiement_id": paiement_tranche.id
        })

    @action(detail=True, methods=['post'])
    def generer_facture(self, request, pk=None):
        """Générer une facture pour un abonnement présentiel"""
        abonnement = self.get_object()
        
        if abonnement.statut_paiement != 'PAIEMENT_TERMINE':
            return Response(
                {"error": "La facture ne peut être générée que lorsque le paiement est terminé"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if abonnement.facture_pdf:
            return Response({
                "message": "Facture déjà générée",
                "facture_url": abonnement.facture_pdf.url
            })
        
        # Générer la facture
        from .utils import generer_facture_pdf
        pdf_file = generer_facture_pdf(abonnement, None, type_ticket='ABONNEMENT')
        abonnement.facture_pdf = pdf_file
        abonnement.save()
        
        return Response({
            "message": "Facture générée avec succès",
            "facture_url": abonnement.facture_pdf.url
        })

    @action(detail=True, methods=['get'])
    def telecharger_facture(self, request, pk=None):
        """Télécharger la facture d'un abonnement présentiel"""
        from django.http import FileResponse, Http404
        from django.conf import settings
        import os
        
        abonnement = self.get_object()
        
        if not abonnement.facture_pdf:
            raise Http404("Facture non trouvée")
        
        try:
            file_path = os.path.join(settings.MEDIA_ROOT, str(abonnement.facture_pdf))
            if os.path.exists(file_path):
                response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                return response
            else:
                raise Http404("Fichier non trouvé sur le serveur")
        except Exception as e:
            raise Http404(f"Erreur lors du téléchargement: {str(e)}")


class PaiementTrancheViewSet(viewsets.ModelViewSet):
    queryset = PaiementTranche.objects.all()
    serializer_class = PaiementTrancheSerializer
    permission_classes = [IsAdminOrEmploye]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['abonnement_presentiel', 'mode_paiement']

    def perform_create(self, serializer):
        # Assigner l'employé qui effectue le paiement
        serializer.save(employe=self.request.user)


# ---------- ViewSets existants ----------
class AbonnementViewSet(viewsets.ModelViewSet):
    queryset = Abonnement.objects.all()
    serializer_class = AbonnementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nom']
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdmin()]
        return [IsAdminOrEmploye()]

    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def clients(self, request, pk=None):
        abonnement = self.get_object()
        clients = User.objects.filter(
            abonnementclient__abonnement=abonnement,
            abonnementclient__actif=True
        )
        serializer = UserSerializer(clients, many=True)
        return Response(serializer.data)


class SeanceViewSet(viewsets.ModelViewSet):
    queryset = Seance.objects.all()
    serializer_class = SeanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['titre']
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsEmploye()]
        return [IsAdminOrEmploye()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def create_v2(self, request, *args, **kwargs):
        print("=== DEBUG SEANCE CREATE ===")
        print("Request data:", request.data)
        print("Request user:", request.user)
        response = super().create(request, *args, **kwargs)
        print("Response data:", response.data)
        return response

    def destroy(self, request, *args, **kwargs):
        try:
            # Récupérer la séance à supprimer
            seance = self.get_object()
            
            # Supprimer d'abord les réservations liées
            seance.reservation_set.all().delete()
            
            # Supprimer les paiements liés
            Paiement.objects.filter(seance=seance).delete()
            
            # Supprimer la séance
            seance.delete()
            
            return Response(
                {"detail": "La séance a été supprimée avec succès."},
                status=status.HTTP_204_NO_CONTENT
            )
            
        except Exception as e:
            return Response(
                {"detail": f"Une erreur est survenue lors de la suppression de la séance: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def coachs(self, request):
        coachs = Personnel.objects.filter(categorie='COACH')
        serializer = PersonnelSerializer(coachs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrEmploye])
    def participants(self, request, pk=None):
        seance = self.get_object()
        participants = User.objects.filter(
            reservation__seance=seance,
            reservation__statut='CONFIRMEE'
        ).distinct()
        serializer = UserSerializer(participants, many=True)
        return Response(serializer.data)


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'seance', 'statut']
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsEmploye()]
        return [IsAdminOrEmploye()]

    def get_queryset(self):
        if self.request.user.role == 'CLIENT':
            return Reservation.objects.filter(client=self.request.user)
        return Reservation.objects.all()

    def perform_create(self, request, *args, **kwargs):
        if self.request.user.role == 'CLIENT':
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)

    def perform_create_v2(self, request, *args, **kwargs):
        # Récupérer le montant avant de sauvegarder la réservation
        montant = self.get_serializer().validated_data.pop('montant', 0)
        type_ticket = self.get_serializer().validated_data.get('type_ticket', 'SEANCE')
        
        # Sauvegarder la réservation avec le client connecté
        reservation = self.get_serializer().save(
            client=self.request.user,
            montant_calcule=montant  # Sauvegarder également le montant dans la réservation
        )
        
        # Créer automatiquement un paiement en attente pour cette réservation
        paiement = Paiement.objects.create(
            client=self.request.user,
            reservation=reservation,
            montant=montant,
            mode_paiement='ESPECE',
            status='EN_ATTENTE'
        )
        
        # Générer le ticket PDF (billet de réservation)
        try:
            pdf_file = generer_facture_pdf(reservation, paiement, type_ticket=type_ticket)
            ticket = Ticket.objects.create(
                paiement=paiement,
                fichier_pdf=pdf_file,
                type_ticket=type_ticket
            )
            print(f"Ticket créé avec succès: {ticket.id} pour la réservation {reservation.id}")
        except Exception as e:
            print(f"Erreur lors de la création du ticket: {str(e)}")
            raise
>>>>>>> f54d897 (Sauvegarde des modifications locales avant mise à jour)


class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.all()
    serializer_class = PaiementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'abonnement', 'seance', 'status']
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsEmploye()]
        return [IsAdminOrEmploye()]

    def get_queryset(self):
        if self.request.user.role == 'CLIENT':
            return Paiement.objects.filter(client=self.request.user)
        return Paiement.objects.all()


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ticket.objects.all()
    # Il faudra créer TicketSerializer
    serializer_class = TicketSerializer
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsEmploye()]
        return [IsAdminOrEmploye()]

    def get_queryset(self):
        if self.request.user.role == 'CLIENT':
            return Ticket.objects.filter(paiement__client=self.request.user)
        return Ticket.objects.all()


class ChargeViewSet(viewsets.ModelViewSet):
    queryset = Charge.objects.all()
    serializer_class = ChargeSerializer
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdmin()]
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
    permission_classes = [IsAdminOrEmploye]

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

class UserListView(generics.ListCreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrEmploye]

    def create(self, request, *args, **kwargs):
        # Vérifier si l'utilisateur a la permission de créer un utilisateur avec ce rôle
        role = request.data.get('role', 'CLIENT')
        if role != 'CLIENT' and not request.user.is_superuser and request.user.role != 'ADMIN':
            return Response(
                {"detail": "Vous n'avez pas la permission de créer un utilisateur avec ce rôle."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Utiliser le sérialiseur d'inscription pour la création
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Renvoyer les données de l'utilisateur créé
            return Response(
                UserSerializer(user).data, 
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
