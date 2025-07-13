# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FinancialReportView, ValiderPaiementView, PaiementDirectView, AbonnementDirectView,
    SeanceDirecteView, AbonnementClientDirectView, ValiderReservationSeanceView,
    ValiderReservationAbonnementView, AbonnementClientReservationView, LoginView,
    RegisterView, MeView,
    AbonnementViewSet, SeanceViewSet, ReservationViewSet,
    PaiementViewSet, TicketViewSet, ChargeViewSet, PresencePersonnelViewSet,
    UserListView, UserReservationsView, PersonnelViewSet,
    AbonnementClientPresentielViewSet, PaiementTrancheViewSet, AbonnementClientViewSet,
    api_root
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register(r'abonnements', AbonnementViewSet)
router.register(r'seances', SeanceViewSet)
router.register(r'reservations', ReservationViewSet)
router.register(r'paiements', PaiementViewSet)
router.register(r'tickets', TicketViewSet)
router.register(r'charges', ChargeViewSet)
router.register(r'presences', PresencePersonnelViewSet)
router.register(r'personnel', PersonnelViewSet)
router.register(r'abonnements-clients', AbonnementClientViewSet)
router.register(r'abonnements-clients-presentiels', AbonnementClientPresentielViewSet)
router.register(r'paiements-tranches', PaiementTrancheViewSet)

urlpatterns = [
    # Racine de l'API
    path('', api_root, name='api-root'),

    # Endpoints manuels (prioritaires)
    path('seances/direct/', SeanceDirecteView.as_view(), name='seance-directe'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/custom/', LoginView.as_view(), name='login-custom'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('financial-report/', FinancialReportView.as_view(), name='financial-report'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:user_id>/reservations/', UserReservationsView.as_view(), name='user-reservations'),
    path('valider-paiement/<int:paiement_id>/', ValiderPaiementView.as_view(), name='valider-paiement'),
    path('paiement-direct/', PaiementDirectView.as_view(), name='paiement-direct'),
    path('abonnement-direct/', AbonnementDirectView.as_view(), name='abonnement-direct'),
    path('abonnements-client/direct/', AbonnementClientDirectView.as_view(), name='abonnement-client-direct'),
    path('reservations/<int:reservation_id>/valider/', ValiderReservationSeanceView.as_view(), name='valider-reservation-seance'),
    path('abonnements-client/<int:ab_client_id>/valider/', ValiderReservationAbonnementView.as_view(), name='valider-reservation-abonnement'),
    path('abonnements-client/reserver/', AbonnementClientReservationView.as_view(), name='abonnement-client-reserver'),

    # Endpoints auto générés par DRF
    path('', include(router.urls)),
]
