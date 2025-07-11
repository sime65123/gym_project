from uuid import uuid4
import time
from datetime import datetime, timedelta
from decimal import Decimal
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
            # Version simplifiée pour diagnostiquer
            print("Test de base - comptage des objets...")
            
            # Compter les objets de base
            paiement_count = Paiement.objects.count()
            charge_count = Charge.objects.count()
            
            print(f"Nombre de paiements: {paiement_count}")
            print(f"Nombre de charges: {charge_count}")
            
            # Test simple des revenus
            print("Test des revenus...")
            total_revenue = Paiement.objects.filter(
                status='PAYE'
            ).aggregate(total=Sum('montant'))['total'] or 0
            
            print(f"Revenus totaux: {total_revenue}")
            
            # Test simple des dépenses
            print("Test des dépenses...")
            total_expenses = Charge.objects.aggregate(
                total=Sum('montant')
            )['total'] or 0
            
            print(f"Dépenses totales: {total_expenses}")
            
            # Réponse simplifiée
            response_data = {
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'total_charges': total_expenses,
                'profit': total_revenue - total_expenses,
                'active_clients': 0,  # Simplifié pour l'instant
                'monthly_stats': [],  # Simplifié pour l'instant
                'subscription_stats': [],  # Simplifié pour l'instant
                'session_stats': []  # Simplifié pour l'instant
            }
            
            print("Réponse finale:", response_data)
            print("Taille de la réponse:", len(str(response_data)))
            
            return Response(response_data)
            
        except Exception as e:
            print(f"Erreur dans FinancialReportView: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Retourner une réponse d'erreur plus détaillée
            error_response = {
                'error': str(e),
                'error_type': type(e).__name__,
                'message': 'Une erreur est survenue lors de la génération du rapport financier'
            }
            
            return Response(
                error_response,
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
    permission_classes = [IsAdminOrEmploye | IsClient]  # Permettre aux clients de lire

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdmin()]  # Seul l'admin peut créer/modifier/supprimer
        # Pour la lecture, on autorise admin, employé et client
        return [permission() for permission in self.permission_classes]
        
    def create(self, request, *args, **kwargs):
        print("Données reçues pour la création d'un abonnement:", request.data)
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print("Erreur lors de la création de l'abonnement:", str(e))
            raise

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
            return [IsAdminOrEmploye()]
        return [IsAdminOrEmploye()]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        
        # Vérifier si un coach_id est fourni et le convertir en entier
        coach_id = data.get('coach_id')
        if coach_id and coach_id != '':
            try:
                data['coach'] = int(coach_id)
            except (ValueError, TypeError):
                return Response(
                    {"error": "Le champ coach doit être un identifiant valide ou null"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            data['coach'] = None
            
        serializer = self.get_serializer(data=data)
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

    def update(self, request, *args, **kwargs):
        """Permet à un employé de modifier une séance"""
        try:
            print("=== DEBUG SEANCE UPDATE ===")
            print("Request data:", request.data)
            print("Request user:", request.user)
            print("User role:", getattr(request.user, 'role', 'Non défini'))
            
            # Vérifier les permissions
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            if request.user.role not in ['ADMIN', 'EMPLOYE']:
                return Response(
                    {'error': 'Permission denied. Only admins and employees can modify sessions.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Récupérer la séance à modifier
            seance = self.get_object()
            print(f"Modifying session: {seance.id} - {seance.client_prenom} {seance.client_nom}")
            
            # Préparer les données
            data = request.data.copy()
            print("Original data:", data)
            
            # Nettoyer et valider les données
            cleaned_data = {}
            
            # Champs de base
            if 'client_nom' in data:
                cleaned_data['client_nom'] = data['client_nom']
            if 'client_prenom' in data:
                cleaned_data['client_prenom'] = data['client_prenom']
            if 'date_jour' in data:
                cleaned_data['date_jour'] = data['date_jour']
            
            # Champs numériques
            if 'nombre_heures' in data:
                try:
                    cleaned_data['nombre_heures'] = int(data['nombre_heures'])
                except (ValueError, TypeError):
                    return Response(
                        {"error": "Le nombre d'heures doit être un nombre entier valide"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if 'montant_paye' in data:
                try:
                    cleaned_data['montant_paye'] = float(data['montant_paye'])
                except (ValueError, TypeError):
                    return Response(
                        {"error": "Le montant payé doit être un nombre valide"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Gestion du coach
            coach_id = data.get('coach_id')
            if coach_id is not None and coach_id != '' and coach_id != 'none' and coach_id != 0:
                try:
                    coach_id_int = int(coach_id)
                    # Vérifier que le coach existe
                    from .models import Personnel
                    coach = Personnel.objects.filter(id=coach_id_int, categorie='COACH').first()
                    if coach:
                        cleaned_data['coach'] = coach
                    else:
                        return Response(
                            {"error": f"Coach avec l'ID {coach_id_int} non trouvé"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except (ValueError, TypeError):
                    return Response(
                        {"error": "Le champ coach_id doit être un identifiant valide"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                cleaned_data['coach'] = None
            
            print("Cleaned data:", cleaned_data)
            
            # Valider et sauvegarder les modifications
            serializer = self.get_serializer(seance, data=cleaned_data, partial=kwargs.get('partial', False))
            
            if not serializer.is_valid():
                print("Validation errors:", serializer.errors)
                return Response(
                    {"error": "Données invalides", "details": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            self.perform_update(serializer)
            
            print("Session updated successfully")
            return Response(serializer.data)
            
        except Exception as e:
            print("=== ERROR IN SEANCE UPDATE ===")
            print("Error type:", type(e))
            print("Error message:", str(e))
            import traceback
            print("Traceback:", traceback.format_exc())
            
            return Response(
                {"error": f"Erreur lors de la modification de la séance: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def partial_update(self, request, *args, **kwargs):
        """Permet à un employé de modifier partiellement une séance"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        try:
            # Récupérer la séance à supprimer
            seance = self.get_object()
            
            # Supprimer d'abord les réservations liées
            seance.reservation_set.all().delete()
            
            # Puis supprimer la séance elle-même
            seance.delete()
            
            return Response(
                {"message": "Séance et réservations associées supprimées avec succès"},
                status=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            return Response(
                {"error": f"Erreur lors de la suppression de la séance: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def coachs(self, request):
        coachs = User.objects.filter(role='COACH')
        serializer = UserSerializer(coachs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def participants(self, request, pk=None):
        seance = self.get_object()
        participants = seance.participants.all()
        serializer = UserSerializer(participants, many=True)
        return Response(serializer.data)


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['nom_client', 'type_reservation', 'statut']
    permission_classes = [IsAdminOrEmploye | IsClient]  

    def get_permissions(self):
        if self.action in ['create_v2', 'create']:
            return [IsClient()]
        # Pour les autres actions, utiliser les permissions définies dans permission_classes
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            # Les clients ne voient que leurs propres réservations
            client_name = f"{user.prenom} {user.nom}"
            return Reservation.objects.filter(nom_client=client_name)
        elif user.is_authenticated and user.role in ['ADMIN', 'EMPLOYE']:
            # Les admins et employés voient toutes les réservations
            return super().get_queryset()
        return Reservation.objects.none()
        
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=True, methods=['post'], permission_classes=[IsEmploye])
    def valider(self, request, pk=None):
        """Permet à un employé de valider une réservation et créer un paiement"""
        try:
            reservation = self.get_object()
            
            # Vérifier que la réservation est en attente
            if reservation.statut != 'EN_ATTENTE':
                return Response(
                    {'error': 'Cette réservation ne peut plus être validée'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer le montant saisi par l'employé
            montant = request.data.get('montant')
            if not montant or float(montant) <= 0:
                return Response(
                    {'error': 'Le montant doit être supérieur à 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculer le montant total déjà payé pour cette réservation
            from django.db.models import Sum
            montant_total_paye = Paiement.objects.filter(
                reservation=reservation,
                status='PAYE'
            ).aggregate(total=Sum('montant'))['total'] or 0
            
            # Convertir en float pour éviter les problèmes de type
            montant_total_paye = float(montant_total_paye) if montant_total_paye else 0.0
            
            # Vérification spécifique pour les abonnements
            if reservation.type_reservation == 'ABONNEMENT':
                # On tente de retrouver l'abonnement par le nom dans la description
                from .models import Abonnement
                try:
                    print(f"=== DEBUG VALIDATION ABONNEMENT ===")
                    print(f"Description de la réservation: {reservation.description}")
                    print(f"Montant de la réservation: {reservation.montant}")
                    print(f"Montant saisi: {montant}")
                    print(f"Montant total déjà payé: {montant_total_paye}")
                    
                    # On suppose que la description contient le nom de l'abonnement (ex: 'Abonnement Gold - ...')
                    nom_abonnement = None
                    if reservation.description:
                        # Cherche le mot après 'Abonnement' dans la description
                        import re
                        match = re.search(r'Abonnement\s+([\w\- ]+)', reservation.description)
                        if match:
                            nom_abonnement = match.group(1).strip()
                            print(f"Nom d'abonnement trouvé: {nom_abonnement}")
                    
                    # Si on ne trouve pas le nom dans la description, on utilise le montant de la réservation
                    if not nom_abonnement:
                        print("Nom d'abonnement non trouvé dans la description, utilisation du montant de la réservation")
                        # On va chercher un abonnement avec un prix proche du montant de la réservation
                        abonnement = Abonnement.objects.filter(
                            prix__gte=reservation.montant * 0.9,  # 10% de tolérance
                            prix__lte=reservation.montant * 1.1
                        ).first()
                    else:
                        abonnement = Abonnement.objects.filter(nom__icontains=nom_abonnement).first()
                    
                    if not abonnement:
                        print("Aucun abonnement trouvé, utilisation du montant de la réservation comme référence")
                        # Si on ne trouve pas d'abonnement, on utilise le montant de la réservation comme référence
                        montant_reference = reservation.montant if reservation.montant > 0 else 5000  # Valeur par défaut
                    else:
                        print(f"Abonnement trouvé: {abonnement.nom} - Prix: {abonnement.prix}")
                        montant_reference = float(abonnement.prix)
                        # Mettre à jour le montant de la réservation si c'est le premier paiement
                        if montant_total_paye == 0:
                            reservation.montant = montant_reference
                            reservation.save()
                            print(f"Montant de la réservation mis à jour: {reservation.montant}")
                    
                    # Vérifier que le montant total payé ne dépasse pas le montant de référence
                    montant_total_apres_paiement = montant_total_paye + float(montant)
                    if montant_total_apres_paiement > float(montant_reference):
                        return Response(
                            {'error': f'Le montant total payé ({montant_total_apres_paiement} FCFA) ne peut pas dépasser le montant de référence ({montant_reference} FCFA)'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    print(f"Validation OK - Montant total après paiement: {montant_total_apres_paiement}")
                    
                except Exception as e:
                    print(f"Erreur lors de la vérification du montant de l'abonnement: {str(e)}")
                    return Response({'error': f'Erreur lors de la vérification du montant de l\'abonnement: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Créer un paiement pour cette réservation
            paiement = Paiement.objects.create(
                client=None,  # Pas de client spécifique pour les réservations
                reservation=reservation,
                montant=float(montant),
                status='PAYE',
                mode_paiement='ESPECE'
            )
            
            # Calculer le nouveau montant total payé
            nouveau_montant_total_paye = montant_total_paye + float(montant)
            
            # Pour les abonnements, vérifier si le paiement est complet
            if reservation.type_reservation == 'ABONNEMENT':
                if nouveau_montant_total_paye >= float(reservation.montant):
                    # Paiement complet, confirmer la réservation
                    reservation.statut = 'CONFIRMEE'
                    reservation.save()
                    
                    # Générer le ticket PDF
                    try:
                        pdf_file = generer_facture_pdf(reservation, paiement, type_ticket=reservation.type_reservation)
                        ticket = Ticket.objects.create(
                            paiement=paiement,
                            fichier_pdf=pdf_file,
                            type_ticket=reservation.type_reservation
                        )
                        print(f"Ticket créé avec succès: {ticket.id} pour la réservation {reservation.id}")
                    except Exception as e:
                        print(f"Erreur lors de la création du ticket: {str(e)}")
                        # Ne pas lever l'exception pour ne pas bloquer la validation
                    
                    return Response({
                        'message': 'Réservation confirmée avec succès - Paiement complet',
                        'paiement_id': paiement.id,
                        'montant': str(paiement.montant),
                        'montant_total_paye': str(nouveau_montant_total_paye),
                        'montant_abonnement': str(reservation.montant),
                        'ticket_url': ticket.fichier_pdf.url if 'ticket' in locals() else None
                    }, status=status.HTTP_200_OK)
                else:
                    # Paiement partiel, garder en attente
                    return Response({
                        'message': 'Paiement partiel enregistré - Réservation en attente',
                        'paiement_id': paiement.id,
                        'montant': str(paiement.montant),
                        'montant_total_paye': str(nouveau_montant_total_paye),
                        'montant_abonnement': str(reservation.montant),
                        'reste_a_payer': str(float(reservation.montant) - nouveau_montant_total_paye)
                    }, status=status.HTTP_200_OK)
            else:
                # Pour les séances, validation immédiate
                reservation.montant = float(montant)  # Correction : mettre à jour le montant de la séance
                reservation.statut = 'CONFIRMEE'
                reservation.save()
                
                # Générer le ticket PDF
                try:
                    pdf_file = generer_facture_pdf(reservation, paiement, type_ticket=reservation.type_reservation)
                    ticket = Ticket.objects.create(
                        paiement=paiement,
                        fichier_pdf=pdf_file,
                        type_ticket=reservation.type_reservation
                    )
                    print(f"Ticket créé avec succès: {ticket.id} pour la réservation {reservation.id}")
                except Exception as e:
                    print(f"Erreur lors de la création du ticket: {str(e)}")
                    # Ne pas lever l'exception pour ne pas bloquer la validation
                
                return Response({
                    'message': 'Réservation validée avec succès',
                    'paiement_id': paiement.id,
                    'montant': str(paiement.montant),
                    'ticket_url': ticket.fichier_pdf.url if 'ticket' in locals() else None
                }, status=status.HTTP_200_OK)
            
        except Reservation.DoesNotExist:
            return Response(
                {'error': 'Réservation introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Erreur lors de la validation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )  

    def create(self, request, *args, **kwargs):
        # Vérifier si l'utilisateur est authentifié
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication credentials were not provided.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
            
        # Ajouter le nom du client connecté à la réservation
        data = request.data.copy()
        data['nom_client'] = f"{request.user.prenom} {request.user.nom}"
        
        # Valider et sauvegarder la réservation
        serializer = self.get_serializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Retourner la réponse avec les données de la réservation créée
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
        
    def perform_create(self, serializer):
        # Sauvegarder la réservation
        reservation = serializer.save()
        
        # Créer automatiquement un paiement en attente pour cette réservation
        try:
            paiement = Paiement.objects.create(
                client=self.request.user if self.request.user.is_authenticated else None,
                reservation=reservation,
                montant=reservation.montant,
                mode_paiement='ESPECE',
                status='EN_ATTENTE'
            )
            
            # Générer le ticket PDF
            try:
                pdf_file = generer_facture_pdf(reservation, paiement, type_ticket=reservation.type_reservation)
                ticket = Ticket.objects.create(
                    paiement=paiement,
                    fichier_pdf=pdf_file,
                    type_ticket=reservation.type_reservation
                )
                print(f"Ticket créé avec succès: {ticket.id} pour la réservation {reservation.id}")
            except Exception as e:
                print(f"Erreur lors de la création du ticket: {str(e)}")
                # Ne pas lever l'exception pour ne pas bloquer la création de la réservation
                
        except Exception as e:
            print(f"Erreur lors de la création du paiement: {str(e)}")
            # Ne pas lever l'exception pour ne pas bloquer la création de la réservation

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

    def destroy(self, request, *args, **kwargs):
        """Permet aux clients de supprimer leurs réservations en attente"""
        try:
            print(f"[DEBUG] Tentative de suppression de réservation - ID: {kwargs.get('pk')}")
            print(f"[DEBUG] Utilisateur: {request.user}")
            print(f"[DEBUG] Rôle: {getattr(request.user, 'role', 'Non défini')}")
            
            reservation = self.get_object()
            print(f"[DEBUG] Réservation trouvée: {reservation.id} - Statut: {reservation.statut}")
            
            # Vérifier que l'utilisateur est le propriétaire de la réservation
            if request.user.role == 'CLIENT':
                client_name = f"{request.user.prenom} {request.user.nom}"
                print(f"[DEBUG] Nom client attendu: {client_name}")
                print(f"[DEBUG] Nom client réservation: {reservation.nom_client}")
                
                if reservation.nom_client != client_name:
                    print(f"[DEBUG] Erreur: nom client ne correspond pas")
                    return Response(
                        {'error': 'Vous ne pouvez supprimer que vos propres réservations'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Vérifier que la réservation est en attente
                if reservation.statut != 'EN_ATTENTE':
                    print(f"[DEBUG] Erreur: réservation pas en attente")
                    return Response(
                        {'error': 'Vous ne pouvez supprimer que les réservations en attente'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Supprimer la réservation
            print(f"[DEBUG] Suppression de la réservation {reservation.id}")
            reservation.delete()
            print(f"[DEBUG] Réservation supprimée avec succès")
            
            return Response(
                {'message': 'Réservation supprimée avec succès'},
                status=status.HTTP_204_NO_CONTENT
            )
            
        except Reservation.DoesNotExist:
            print(f"[DEBUG] Réservation introuvable")
            return Response(
                {'error': 'Réservation introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"[DEBUG] Erreur lors de la suppression: {str(e)}")
            return Response(
                {'error': f'Erreur lors de la suppression: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.all()
    serializer_class = PaiementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'abonnement', 'seance', 'status']
    permission_classes = [IsAdminOrEmploye | IsClient]  # Permettre aux clients de lire

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdmin()]  # Seul l'admin peut créer/modifier/supprimer
        # Pour la lecture, on autorise admin, employé et client
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            # Les clients ne voient que leurs propres paiements
            return Paiement.objects.filter(client=user)
        elif user.is_authenticated and user.role in ['ADMIN', 'EMPLOYE']:
            # Les admins et employés voient tous les paiements
            return super().get_queryset()
        return Paiement.objects.none()  # Aucun résultat si non authentifié


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAdminOrEmploye | IsClient]  # Permettre aux clients de lire

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdmin()]  # Seul l'admin peut créer/modifier/supprimer
        # Pour la lecture, on autorise admin, employé et client
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            # Les clients ne voient que leurs propres tickets
            return Ticket.objects.filter(paiement__client=user)
        elif user.is_authenticated and user.role in ['ADMIN', 'EMPLOYE']:
            # Les admins et employés voient tous les tickets
            return super().get_queryset().order_by('-id')  # Tri par ID décroissant
        return Ticket.objects.none()  # Aucun résultat si non authentifié


class ChargeViewSet(viewsets.ModelViewSet):
    queryset = Charge.objects.all()
    serializer_class = ChargeSerializer
    permission_classes = [IsAdminOrEmploye]

    def get_permissions(self):
        # Permettre aux admins et employés de créer/modifier/supprimer
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdminOrEmploye()]
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

class UserReservationsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, user_id):
        """Récupérer toutes les réservations confirmées d'un client spécifique"""
        try:
            user = User.objects.get(id=user_id)
            
            # Vérifier que l'utilisateur est un client
            if user.role != 'CLIENT':
                return Response(
                    {'error': 'Cet utilisateur n\'est pas un client'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer les réservations confirmées du client
            client_name = f"{user.prenom} {user.nom}"
            reservations = Reservation.objects.filter(
                nom_client=client_name,
                statut='CONFIRMEE'
            ).order_by('-created_at')
            
            # Sérialiser les réservations
            from .serializers import ReservationSerializer
            serializer = ReservationSerializer(reservations, many=True)
            
            return Response({
                'client': {
                    'id': user.id,
                    'nom': user.nom,
                    'prenom': user.prenom,
                    'email': user.email
                },
                'reservations': serializer.data,
                'total_reservations': reservations.count()
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'Utilisateur introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Erreur lors de la récupération des réservations: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
        
        # Récupérer le montant depuis la requête ou utiliser celui de la séance
        montant = request.data.get('montant')
        if montant is not None:
            try:
                montant = float(montant)
                if montant <= 0:
                    return Response({'error': 'Le montant doit être supérieur à zéro'}, status=400)
            except (ValueError, TypeError):
                return Response({'error': 'Montant invalide'}, status=400)
        else:
            montant = reservation.seance.montant_paye or 0
        
        # Mettre à jour la réservation avec le montant payé et le montant total
        reservation.statut = 'CONFIRMEE'
        reservation.montant_paye = Decimal(str(montant))  # Convertir en Decimal pour la base de données
        reservation.montant = Decimal(str(montant))  # Mettre à jour le montant total avec le montant payé
        reservation.save()
        
        # Créer le paiement
        paiement = Paiement.objects.create(
            client=reservation.client,
            seance=reservation.seance,
            montant=Decimal(str(montant)),
            status='PAYE',
            mode_paiement=request.data.get('mode_paiement', 'ESPECE'),
            reservation=reservation
        )
        
        # Rafraîchir l'objet pour s'assurer d'avoir les dernières données
        reservation.refresh_from_db()
        
        # Générer le ticket PDF
        pdf_file = generer_facture_pdf(reservation.seance, paiement, type_ticket='SEANCE')
        ticket = Ticket.objects.create(
            paiement=paiement,
            fichier_pdf=pdf_file,
            type_ticket='SEANCE'
        )
        
        # Sérializer la réservation mise à jour pour la réponse
        from .serializers import ReservationSerializer
        serializer = ReservationSerializer(reservation, context={'request': request})
        
        # Forcer la mise à jour des données dans la réponse
        response_data = serializer.data
        response_data['montant'] = str(reservation.montant)
        response_data['montant_paye'] = str(reservation.montant_paye)
        
        return Response({
            'message': 'Réservation validée et facture générée.',
            'reservation': response_data,
            'ticket_id': ticket.id, 
            'ticket_pdf_url': ticket.fichier_pdf.url if ticket.fichier_pdf else None
        })

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
    permission_classes = [IsAdminOrEmploye | IsClient]  # Permettre aux clients de lire
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['client', 'abonnement', 'actif']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'CLIENT':
            # Les clients ne voient que leurs propres abonnements
            return AbonnementClient.objects.filter(client=user)
        elif user.is_authenticated and user.role in ['ADMIN', 'EMPLOYE']:
            # Les admins et employés voient tous les abonnements
            return super().get_queryset()
        return AbonnementClient.objects.none()  # Aucun résultat si non authentifié

class LoginView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    permission_classes = []
