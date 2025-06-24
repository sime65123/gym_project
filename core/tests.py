import pytest
import json
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import (
    User, Abonnement, Seance, Reservation,
    Paiement, Facture, Charge, PresencePersonnel
)


# ---------------------- Fixtures ----------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user():
    return User.objects.create_user(
        email='admin@example.com',
        password='password123',
        nom='Admin',
        prenom='User',
        role='ADMIN',
        is_staff=True,
        is_superuser=True
    )


@pytest.fixture
def employee_user():
    return User.objects.create_user(
        email='employee@example.com',
        password='password123',
        nom='Employee',
        prenom='User',
        role='EMPLOYE'
    )


@pytest.fixture
def client_user():
    return User.objects.create_user(
        email='client@example.com',
        password='password123',
        nom='Client',
        prenom='User',
        role='CLIENT',
        telephone='1234567890',
        solde=Decimal('100.00')
    )


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    url = reverse('token_obtain_pair')
    response = api_client.post(
        url, {'email': admin_user.email, 'password': 'password123'}, format='json'
    )
    token = response.data['access']
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client


@pytest.fixture
def authenticated_employee_client(api_client, employee_user):
    url = reverse('token_obtain_pair')
    response = api_client.post(
        url, {'email': employee_user.email, 'password': 'password123'}, format='json'
    )
    token = response.data['access']
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client


@pytest.fixture
def authenticated_client_client(api_client, client_user):
    url = reverse('token_obtain_pair')
    response = api_client.post(
        url, {'email': client_user.email, 'password': 'password123'}, format='json'
    )
    token = response.data['access']
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client


@pytest.fixture
def abonnement():
    return Abonnement.objects.create(
        nom='Abonnement Test',
        description='Description test',
        prix=Decimal('50.00'),
        duree_jours=30,
        actif=True
    )


@pytest.fixture
def seance(employee_user):
    return Seance.objects.create(
        titre='Séance Test',
        description='Description test',
        date_heure=timezone.now() + timedelta(days=1),
        coach=employee_user,
        capacite=10
    )


@pytest.fixture
def reservation(client_user, seance):
    return Reservation.objects.create(
        client=client_user,
        seance=seance,
        statut='CONFIRMEE'
    )


@pytest.fixture
def paiement(client_user, abonnement):
    return Paiement.objects.create(
        client=client_user,
        abonnement=abonnement,
        montant=Decimal('50.00'),
        status='PAYE',
        mode_paiement='CINETPAY',
        transaction_id=f"{client_user.id}-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def facture(paiement):
    return Facture.objects.create(
        paiement=paiement,
        fichier_pdf='factures/test.pdf'
    )


@pytest.fixture
def charge():
    return Charge.objects.create(
        titre='Charge Test',
        montant=Decimal('100.00'),
        date=timezone.now().date(),
        description='Description test'
    )


@pytest.fixture
def presence_personnel(employee_user):
    return PresencePersonnel.objects.create(
        employe=employee_user,
        date=timezone.now().date(),
        present=True
    )


# ---------------------- Authentication Tests ----------------------

@pytest.mark.django_db
class TestAuthentication:
    def test_register_user(self, api_client):
        url = reverse('register')
        data = {
            'email': 'newuser@example.com',
            'nom': 'New',
            'prenom': 'User',
            'password': 'password123'
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email='newuser@example.com').exists()
        user = User.objects.get(email='newuser@example.com')
        assert user.role == 'CLIENT'  # Default role should be CLIENT

    def test_login_user(self, api_client, client_user):
        url = reverse('token_obtain_pair')
        data = {
            'email': client_user.email,
            'password': 'password123'
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_refresh_token(self, api_client, client_user):
        # First get a token
        url = reverse('token_obtain_pair')
        data = {
            'email': client_user.email,
            'password': 'password123'
        }
        response = api_client.post(url, data, format='json')
        refresh_token = response.data['refresh']

        # Then refresh it
        url = reverse('token_refresh')
        data = {'refresh': refresh_token}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_me_endpoint(self, authenticated_client_client, client_user):
        url = reverse('me')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == client_user.email
        assert response.data['nom'] == client_user.nom
        assert response.data['prenom'] == client_user.prenom
        assert response.data['role'] == client_user.role
        assert Decimal(response.data['solde']) == client_user.solde

    def test_update_profile(self, authenticated_client_client, client_user):
        url = reverse('me')
        data = {
            'nom': 'Updated',
            'prenom': 'Name',
            'telephone': '9876543210'
        }
        response = authenticated_client_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        client_user.refresh_from_db()
        assert client_user.nom == 'Updated'
        assert client_user.prenom == 'Name'
        assert client_user.telephone == '9876543210'


# ---------------------- Abonnement Tests ----------------------

@pytest.mark.django_db
class TestAbonnement:
    def test_list_abonnements(self, authenticated_client_client, abonnement):
        url = reverse('abonnements-list')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['nom'] == abonnement.nom

    def test_create_abonnement_as_admin(self, authenticated_admin_client):
        url = reverse('abonnements-list')
        data = {
            'nom': 'Nouvel Abonnement',
            'description': 'Description',
            'prix': '75.00',
            'duree_jours': 60,
            'actif': True
        }
        response = authenticated_admin_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert Abonnement.objects.filter(nom='Nouvel Abonnement').exists()

    def test_create_abonnement_as_client_forbidden(self, authenticated_client_client):
        url = reverse('abonnements-list')
        data = {
            'nom': 'Nouvel Abonnement',
            'description': 'Description',
            'prix': '75.00',
            'duree_jours': 60,
            'actif': True
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_abonnement(self, authenticated_admin_client, abonnement):
        url = reverse('abonnements-detail', args=[abonnement.id])
        data = {
            'prix': '60.00',
            'actif': False
        }
        response = authenticated_admin_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        abonnement.refresh_from_db()
        assert abonnement.prix == Decimal('60.00')
        assert abonnement.actif is False

    def test_delete_abonnement(self, authenticated_admin_client, abonnement):
        url = reverse('abonnements-detail', args=[abonnement.id])
        response = authenticated_admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Abonnement.objects.filter(id=abonnement.id).exists()


# ---------------------- Seance Tests ----------------------

@pytest.mark.django_db
class TestSeance:
    def test_list_seances(self, authenticated_client_client, seance):
        url = reverse('seances-list')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['titre'] == seance.titre

    def test_create_seance_as_employee(self, authenticated_employee_client, employee_user):
        url = reverse('seances-list')
        data = {
            'titre': 'Nouvelle Séance',
            'description': 'Description',
            'date_heure': (timezone.now() + timedelta(days=2)).isoformat(),
            'coach': employee_user.id,
            'capacite': 15
        }
        response = authenticated_employee_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert Seance.objects.filter(titre='Nouvelle Séance').exists()

    def test_create_seance_as_client_forbidden(self, authenticated_client_client, employee_user):
        url = reverse('seances-list')
        data = {
            'titre': 'Nouvelle Séance',
            'description': 'Description',
            'date_heure': (timezone.now() + timedelta(days=2)).isoformat(),
            'coach': employee_user.id,
            'capacite': 15
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_seance(self, authenticated_employee_client, seance):
        url = reverse('seances-detail', args=[seance.id])
        data = {
            'capacite': 20,
            'description': 'Updated description'
        }
        response = authenticated_employee_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        seance.refresh_from_db()
        assert seance.capacite == 20
        assert seance.description == 'Updated description'

    def test_delete_seance(self, authenticated_admin_client, seance):
        url = reverse('seances-detail', args=[seance.id])
        response = authenticated_admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Seance.objects.filter(id=seance.id).exists()


# ---------------------- Reservation Tests ----------------------

@pytest.mark.django_db
class TestReservation:
    def test_list_reservations(self, authenticated_client_client, reservation):
        url = reverse('reservations-list')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['seance'] == str(reservation.seance)

    def test_create_reservation(self, authenticated_client_client, seance):
        url = reverse('reservations-list')
        data = {
            'seance': seance.id
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert Reservation.objects.filter(seance=seance).exists()

    def test_update_reservation_status(self, authenticated_client_client, reservation):
        url = reverse('reservations-detail', args=[reservation.id])
        data = {
            'statut': 'ANNULEE'
        }
        response = authenticated_client_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        reservation.refresh_from_db()
        assert reservation.statut == 'ANNULEE'

    def test_delete_reservation(self, authenticated_client_client, reservation):
        url = reverse('reservations-detail', args=[reservation.id])
        response = authenticated_client_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Reservation.objects.filter(id=reservation.id).exists()


# ---------------------- Payment Tests ----------------------

@pytest.mark.django_db
class TestPaiement:
    def test_list_paiements(self, authenticated_client_client, paiement):
        url = reverse('paiements-list')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['montant'] == '50.00'

    @patch('core.views.cinetpay_client.initialize_transaction')
    def test_init_paiement_cinetpay(self, mock_initialize, authenticated_client_client, abonnement):
        # Mock CinetPay response
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json = {'payment_url': 'https://cinetpay.com/payment/123'}
        mock_initialize.return_value = mock_response

        url = reverse('init-paiement')
        data = {
            'montant': '50.00',
            'abonnement': abonnement.id
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'paiement_id' in response.data
        assert 'transaction_id' in response.data
        assert 'cinetpay_response' in response.data
        assert Paiement.objects.filter(abonnement=abonnement).exists()

    def test_paiement_with_balance(self, authenticated_client_client, client_user, abonnement):
        url = reverse('init-paiement')
        data = {
            'montant': '50.00',
            'abonnement': abonnement.id,
            'use_balance': True
        }
        initial_balance = client_user.solde
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'PAYE'
        client_user.refresh_from_db()
        assert client_user.solde == initial_balance - Decimal('50.00')
        assert Paiement.objects.filter(
            abonnement=abonnement, 
            status='PAYE', 
            mode_paiement='SOLDE'
        ).exists()

    def test_insufficient_balance(self, authenticated_client_client, client_user, abonnement):
        url = reverse('init-paiement')
        data = {
            'montant': '200.00',  # More than the client's balance of 100.00
            'abonnement': abonnement.id,
            'use_balance': True
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Solde insuffisant' in response.data['error']

    @patch('core.views.cinetpay_client.get_transaction')
    def test_cinetpay_webhook_success(self, mock_get_transaction, api_client, paiement):
        # Set payment to pending
        paiement.status = 'EN_ATTENTE'
        paiement.save()

        # Mock CinetPay response
        mock_response = MagicMock()
        mock_response.json = {'cpm_result': '00'}  # Success code
        mock_get_transaction.return_value = mock_response

        url = reverse('cinetpay-webhook')
        data = {'cpm_trans_id': paiement.transaction_id}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        paiement.refresh_from_db()
        assert paiement.status == 'PAYE'

    @patch('core.views.cinetpay_client.get_transaction')
    def test_cinetpay_webhook_recharge(self, mock_get_transaction, api_client, client_user):
        # Create a recharge payment
        paiement = Paiement.objects.create(
            client=client_user,
            montant=Decimal('50.00'),
            status='EN_ATTENTE',
            mode_paiement='CINETPAY',
            transaction_id=f"recharge-{client_user.id}-{uuid.uuid4().hex[:8]}"
        )
        initial_balance = client_user.solde

        # Mock CinetPay response
        mock_response = MagicMock()
        mock_response.json = {'cpm_result': '00'}  # Success code
        mock_get_transaction.return_value = mock_response

        url = reverse('cinetpay-webhook')
        data = {'cpm_trans_id': paiement.transaction_id}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        paiement.refresh_from_db()
        assert paiement.status == 'PAYE'
        client_user.refresh_from_db()
        assert client_user.solde == initial_balance + Decimal('50.00')

    def test_recharge_compte_view(self, authenticated_client_client):
        with patch('core.views.cinetpay_client.initialize_transaction') as mock_initialize:
            # Mock CinetPay response
            mock_response = MagicMock()
            mock_response.status_code = status.HTTP_200_OK
            mock_response.json = {'payment_url': 'https://cinetpay.com/payment/123'}
            mock_initialize.return_value = mock_response

            url = reverse('recharge-compte')
            data = {'montant': '50.00'}
            response = authenticated_client_client.post(url, data, format='json')
            assert response.status_code == status.HTTP_200_OK
            assert 'paiement_id' in response.data
            assert 'transaction_id' in response.data
            assert response.data['transaction_id'].startswith('recharge-')
            assert Paiement.objects.filter(
                transaction_id__startswith='recharge-',
                status='EN_ATTENTE'
            ).exists()


# ---------------------- Facture Tests ----------------------

@pytest.mark.django_db
class TestFacture:
    def test_list_factures(self, authenticated_client_client, facture):
        url = reverse('factures-list')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert str(facture.uuid) in response.data['results'][0]['uuid']

    def test_get_facture_detail(self, authenticated_client_client, facture):
        url = reverse('factures-detail', args=[facture.id])
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert str(facture.uuid) in response.data['uuid']
        assert 'fichier_pdf_url' in response.data

    def test_facture_generation_after_payment(self, api_client, paiement):
        # Set up a payment that will trigger invoice generation
        paiement.status = 'EN_ATTENTE'
        paiement.save()

        # Mock CinetPay response
        with patch('core.views.cinetpay_client.get_transaction') as mock_get_transaction:
            mock_response = MagicMock()
            mock_response.json = {'cpm_result': '00'}  # Success code
            mock_get_transaction.return_value = mock_response

            # Trigger the webhook
            url = reverse('cinetpay-webhook')
            data = {'cpm_trans_id': paiement.transaction_id}
            response = api_client.post(url, data, format='json')
            assert response.status_code == status.HTTP_200_OK

            # Check if an invoice was generated
            assert Facture.objects.filter(paiement=paiement).exists()


# ---------------------- Charge Tests ----------------------

@pytest.mark.django_db
class TestCharge:
    def test_list_charges(self, authenticated_admin_client, charge):
        url = reverse('charges-list')
        response = authenticated_admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['titre'] == charge.titre

    def test_create_charge(self, authenticated_admin_client):
        url = reverse('charges-list')
        data = {
            'titre': 'Nouvelle Charge',
            'montant': '150.00',
            'date': timezone.now().date().isoformat(),
            'description': 'Description test'
        }
        response = authenticated_admin_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert Charge.objects.filter(titre='Nouvelle Charge').exists()

    def test_create_charge_as_client_forbidden(self, authenticated_client_client):
        url = reverse('charges-list')
        data = {
            'titre': 'Nouvelle Charge',
            'montant': '150.00',
            'date': timezone.now().date().isoformat(),
            'description': 'Description test'
        }
        response = authenticated_client_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_charge(self, authenticated_admin_client, charge):
        url = reverse('charges-detail', args=[charge.id])
        data = {
            'montant': '200.00',
            'description': 'Updated description'
        }
        response = authenticated_admin_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        charge.refresh_from_db()
        assert charge.montant == Decimal('200.00')
        assert charge.description == 'Updated description'

    def test_delete_charge(self, authenticated_admin_client, charge):
        url = reverse('charges-detail', args=[charge.id])
        response = authenticated_admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Charge.objects.filter(id=charge.id).exists()


# ---------------------- PresencePersonnel Tests ----------------------

@pytest.mark.django_db
class TestPresencePersonnel:
    def test_list_presences(self, authenticated_employee_client, presence_personnel):
        url = reverse('presences-list')
        response = authenticated_employee_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['employe'] == str(presence_personnel.employe)

    def test_create_presence(self, authenticated_employee_client, employee_user):
        url = reverse('presences-list')
        data = {
            'employe': employee_user.id,
            'date': (timezone.now().date() + timedelta(days=1)).isoformat(),
            'present': True,
            'commentaire': 'Présent toute la journée'
        }
        response = authenticated_employee_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert PresencePersonnel.objects.filter(
            employe=employee_user,
            date=timezone.now().date() + timedelta(days=1)
        ).exists()

    def test_update_presence(self, authenticated_employee_client, presence_personnel):
        url = reverse('presences-detail', args=[presence_personnel.id])
        data = {
            'present': False,
            'commentaire': 'Absent pour maladie'
        }
        response = authenticated_employee_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        presence_personnel.refresh_from_db()
        assert presence_personnel.present is False
        assert presence_personnel.commentaire == 'Absent pour maladie'

    def test_delete_presence(self, authenticated_employee_client, presence_personnel):
        url = reverse('presences-detail', args=[presence_personnel.id])
        response = authenticated_employee_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PresencePersonnel.objects.filter(id=presence_personnel.id).exists()


# ---------------------- Financial Report Tests ----------------------

@pytest.mark.django_db
class TestFinancialReport:
    def test_financial_report_access_admin(self, authenticated_admin_client, paiement, charge):
        url = reverse('financial-report')
        response = authenticated_admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'summary' in response.data
        assert 'monthly' in response.data
        assert 'subscriptions' in response.data
        assert 'sessions' in response.data
        
        # Check summary data
        assert 'total_revenue' in response.data['summary']
        assert 'total_expenses' in response.data['summary']
        assert 'profit' in response.data['summary']
        assert 'active_clients' in response.data['summary']
        
        # Verify calculations
        assert Decimal(response.data['summary']['total_revenue']) == paiement.montant
        assert Decimal(response.data['summary']['total_expenses']) == charge.montant
        assert Decimal(response.data['summary']['profit']) == paiement.montant - charge.montant

    def test_financial_report_access_client_forbidden(self, authenticated_client_client):
        url = reverse('financial-report')
        response = authenticated_client_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN