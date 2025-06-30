from rest_framework import serializers
from .models import User
from django.contrib.auth import authenticate
from .models import AbonnementClient, AbonnementClientPresentiel, PaiementTranche, HistoriquePaiement
from .models import Ticket
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.conf import settings

class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    telephone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default='CLIENT', required=False)

    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'password', 'telephone', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role', 'CLIENT')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            nom=validated_data['nom'],
            prenom=validated_data['prenom'],
            telephone=validated_data.get('telephone', ''),
            role=role
        )
        return user

class UserSerializer(serializers.ModelSerializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'nom', 'prenom', 'telephone', 'role', 'current_password', 'new_password']
        read_only_fields = ['id', 'role']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
            'email': {'required': True},
            'nom': {'required': True},
            'prenom': {'required': True},
            'telephone': {'required': False, 'allow_blank': True}
        }

    def create(self, validated_data):
        # Créer un nouvel utilisateur avec le mot de passe haché
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user
        
    def update(self, instance, validated_data):
        # Mettre à jour les champs de base
        instance.email = validated_data.get('email', instance.email)
        instance.nom = validated_data.get('nom', instance.nom)
        instance.prenom = validated_data.get('prenom', instance.prenom)
        instance.telephone = validated_data.get('telephone', instance.telephone)
        
        # Gérer la mise à jour du mot de passe
        current_password = validated_data.get('current_password')
        new_password = validated_data.get('new_password') or validated_data.get('password')
        
        if new_password:
            # Vérifier que l'ancien mot de passe est fourni et correct
            if not current_password:
                raise serializers.ValidationError({
                    'current_password': 'Le mot de passe actuel est requis pour modifier le mot de passe.'
                })
                
            if not instance.check_password(current_password):
                raise serializers.ValidationError({
                    'current_password': 'Le mot de passe actuel est incorrect.'
                })
                
            # Définir le nouveau mot de passe
            instance.set_password(new_password)
        
        instance.save()
        return instance

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
    montant = serializers.DecimalField(max_digits=10, decimal_places=2, required=True, write_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'client', 'client_nom', 'client_prenom', 'seance', 'seance_titre', 'date_reservation', 'statut', 'paye', 'date_heure_souhaitee', 'nombre_heures', 'montant', 'montant_calcule', 'description']
        read_only_fields = ['client', 'date_reservation', 'montant_calcule']

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

class PaiementTrancheSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source='employe.nom', read_only=True)
    employe_prenom = serializers.CharField(source='employe.prenom', read_only=True)
    
    class Meta:
        model = PaiementTranche
        fields = ['id', 'abonnement_presentiel', 'montant', 'date_paiement', 'mode_paiement', 'employe', 'employe_nom', 'employe_prenom']
        read_only_fields = ['date_paiement']

class HistoriquePaiementSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source='abonnement_presentiel.client_nom', read_only=True)
    client_prenom = serializers.CharField(source='abonnement_presentiel.client_prenom', read_only=True)
    
    class Meta:
        model = HistoriquePaiement
        fields = ['id', 'abonnement_presentiel', 'montant_ajoute', 'montant_total_apres', 'date_modification', 'client_nom', 'client_prenom']
        read_only_fields = ['date_modification']

class AbonnementClientPresentielSerializer(serializers.ModelSerializer):
    abonnement_nom = serializers.CharField(source='abonnement.nom', read_only=True)
    abonnement_prix = serializers.DecimalField(source='abonnement.prix', read_only=True, max_digits=10, decimal_places=2)
    employe_nom = serializers.CharField(source='employe_creation.nom', read_only=True)
    employe_prenom = serializers.CharField(source='employe_creation.prenom', read_only=True)
    paiements_tranches = PaiementTrancheSerializer(many=True, read_only=True)
    historique_paiements = HistoriquePaiementSerializer(many=True, read_only=True)
    facture_pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AbonnementClientPresentiel
        fields = [
            'id', 'client', 'client_nom', 'client_prenom', 'abonnement', 'abonnement_nom', 
            'abonnement_prix', 'date_debut', 'date_fin', 'montant_total', 'montant_paye', 
            'statut_paiement', 'statut', 'date_creation', 'employe_creation', 'employe_nom', 
            'employe_prenom', 'paiements_tranches', 'historique_paiements', 'facture_pdf_url'
        ]
        read_only_fields = ['date_creation', 'montant_total', 'statut_paiement', 'statut', 'date_fin']
    
    def get_facture_pdf_url(self, obj):
        if obj.facture_pdf:
            try:
                request = self.context.get('request')
                if request is not None:
                    # Construire l'URL absolue
                    url = request.build_absolute_uri(obj.facture_pdf.url)
                    print(f"Generated URL: {url}")
                    return url
                else:
                    # Fallback si pas de request
                    url = f"{settings.MEDIA_URL}{obj.facture_pdf.name}"
                    print(f"Fallback URL: {url}")
                    return url
            except Exception as e:
                print(f"Error generating URL: {e}")
                # Retourner l'URL relative en dernier recours
                return obj.facture_pdf.url
        return None

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
