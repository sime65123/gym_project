from rest_framework import serializers
from .models import User
from django.contrib.auth import authenticate
from .models import AbonnementClient
from .models import Ticket
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.conf import settings

class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            nom=validated_data['nom'],
            prenom=validated_data['prenom'],
            role='CLIENT'
        )
        return user

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'nom', 'prenom', 'role']

from .models import (
    Abonnement, Seance, Reservation, Paiement,
    Ticket, Charge, PresencePersonnel, User, Personnel
)

class AbonnementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Abonnement
        fields = '__all__'

class PersonnelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Personnel
        fields = '__all__'

class SeanceSerializer(serializers.ModelSerializer):
    ticket_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Seance
        fields = [
            'id', 'client_nom', 'client_prenom', 'date_jour', 'nombre_heures', 'montant_paye',
            'ticket_url'
        ]
    
    def get_ticket_url(self, obj):
        try:
            paiement = obj.paiement_set.first()
            if paiement and hasattr(paiement, 'ticket') and paiement.ticket:
                request = self.context.get('request')
                url = paiement.ticket.fichier_pdf.url
                if request is not None:
                    return request.build_absolute_uri(url)
                # fallback
                return f"{settings.MEDIA_URL}{url}"
        except:
            pass
        return None

class ReservationSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    client_nom = serializers.CharField(source='client.nom', read_only=True)
    client_prenom = serializers.CharField(source='client.prenom', read_only=True)
    seance_titre = serializers.CharField(source='seance.titre', read_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'client', 'client_nom', 'client_prenom', 'seance', 'seance_titre', 'date_reservation', 'statut', 'paye', 'date_heure_souhaitee', 'nombre_heures', 'montant_calcule', 'description']
        read_only_fields = ['client', 'date_reservation']

class PaiementSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    abonnement = serializers.StringRelatedField(read_only=True)
    seance = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Paiement
        fields = '__all__'
        read_only_fields = ['client', 'date_paiement']

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = '__all__'

class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Charge
        fields = '__all__'

class BlankableTimeField(serializers.TimeField):
    def to_internal_value(self, value):
        if value in ("", None):
            return None
        return super().to_internal_value(value)

class PresencePersonnelSerializer(serializers.ModelSerializer):
    personnel = PersonnelSerializer(read_only=True)
    personnel_id = serializers.PrimaryKeyRelatedField(
        queryset=Personnel.objects.all(), 
        source='personnel', 
        write_only=True, 
        required=False, 
        allow_null=True
    )
    employe = UserSerializer(read_only=True)
    employe_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='EMPLOYE'), 
        source='employe', 
        write_only=True, 
        required=False, 
        allow_null=True
    )
    heure_arrivee = BlankableTimeField(required=False, allow_null=True)

    class Meta:
        model = PresencePersonnel
        fields = ['id', 'personnel', 'personnel_id', 'employe', 'employe_id', 'statut', 'heure_arrivee', 'date_jour']

    def validate(self, data):
        # Si le statut est ABSENT, on force heure_arrivee à None
        if data.get('statut') == 'ABSENT':
            data['heure_arrivee'] = None
        # Si heure_arrivee est une chaîne vide, absente ou non conforme, on la met à None
        if not data.get('heure_arrivee') or data.get('heure_arrivee') in ['', None]:
            data['heure_arrivee'] = None
        return data

    def create(self, validated_data):
        print("=== DEBUG SERIALIZER CREATE ===")
        print("Validated data before:", validated_data)
        
        # Récupérer l'utilisateur depuis le contexte de la requête
        request = self.context.get('request')
        print("Request user:", request.user if request else "No request")
        
        if request and request.user and request.user.role == 'EMPLOYE':
            # Si c'est un employé et qu'aucun personnel ou employe n'est spécifié, 
            # c'est l'employé qui marque sa propre présence
            if not validated_data.get('personnel') and not validated_data.get('employe'):
                print("Setting employe to current user:", request.user)
                validated_data['employe'] = request.user
        
        print("Validated data after:", validated_data)
        
        try:
            instance = super().create(validated_data)
            print("Instance created successfully:", instance)
            return instance
        except Exception as e:
            print("=== ERROR IN SERIALIZER CREATE ===")
            print("Error type:", type(e))
            print("Error message:", str(e))
            import traceback
            print("Traceback:", traceback.format_exc())
            raise

class AbonnementClientSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source='client.nom', read_only=True)
    client_prenom = serializers.CharField(source='client.prenom', read_only=True)
    abonnement_nom = serializers.CharField(source='abonnement.nom', read_only=True)
    class Meta:
        model = AbonnementClient
        fields = ['id', 'client', 'client_nom', 'client_prenom', 'abonnement', 'abonnement_nom', 'date_debut', 'date_fin', 'actif', 'paiement']

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        return token

    def validate(self, attrs):
        attrs['username'] = attrs.get('email')
        return super().validate(attrs)
