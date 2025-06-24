from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaiementInitAPIView, CinetPayWebhook, FinancialReportView, RechargeCompteView
from .views import (
    RegisterView, MeView,
    AbonnementViewSet, SeanceViewSet, ReservationViewSet,
    PaiementViewSet, FactureViewSet, ChargeViewSet, PresencePersonnelViewSet,
    UserListView, UserDetailView, PersonnelViewSet
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register(r'abonnements', AbonnementViewSet)
router.register(r'seances', SeanceViewSet)
router.register(r'reservations', ReservationViewSet)
router.register(r'paiements', PaiementViewSet)
router.register(r'factures', FactureViewSet)
router.register(r'charges', ChargeViewSet)
router.register(r'presences', PresencePersonnelViewSet)
router.register(r'personnel', PersonnelViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('init-paiement/', PaiementInitAPIView.as_view(), name='init-paiement'),
    path('cinetpay/notify/', CinetPayWebhook.as_view(), name='cinetpay-webhook'),
    path('financial-report/', FinancialReportView.as_view(), name='financial-report'),
    path('recharge-compte/', RechargeCompteView.as_view(), name='recharge-compte'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
]

