from rest_framework import serializers
from .models import User
from django.contrib.auth import authenticate

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
        fields = ['id', 'email', 'nom', 'prenom', 'telephone', 'role', 'solde']



from .models import (
    Abonnement, Seance, Reservation, Paiement,
    Facture, Charge, PresencePersonnel, User, Personnel
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
    coach = PersonnelSerializer(read_only=True)
    coach_id = serializers.PrimaryKeyRelatedField(
        queryset=Personnel.objects.filter(categorie='COACH'), 
        source='coach', 
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Seance
        fields = '__all__'


class ReservationSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = ['client', 'date_reservation']



class PaiementSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    abonnement = serializers.StringRelatedField(read_only=True)
    seance = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Paiement
        fields = '__all__'
        read_only_fields = ['client', 'date_paiement']



class FactureSerializer(serializers.ModelSerializer):
    fichier_pdf_url = serializers.SerializerMethodField()
    paiement = PaiementSerializer(read_only=True)

    class Meta:
        model = Facture
        fields = ['id', 'uuid', 'date_generation', 'paiement', 'fichier_pdf_url']

    def get_fichier_pdf_url(self, obj):
        request = self.context.get('request')
        if obj.fichier_pdf and hasattr(obj.fichier_pdf, 'url'):
            return request.build_absolute_uri(obj.fichier_pdf.url)
        return None



class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Charge
        fields = '__all__'


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
    heure_arrivee = serializers.TimeField(required=False, allow_null=True)

    class Meta:
        model = PresencePersonnel
        fields = ['id', 'personnel', 'personnel_id', 'employe', 'employe_id', 'statut', 'heure_arrivee', 'date_jour']

    def validate(self, data):
        print("=== DEBUG VALIDATE ===")
        print("Data received:", data)
        
        # Si le statut est ABSENT, on s'assure que heure_arrivee est None
        if data.get('statut') == 'ABSENT':
            data['heure_arrivee'] = None
        
        # Si heure_arrivee est une chaîne vide ou None, on la met à None
        if data.get('heure_arrivee') == '' or data.get('heure_arrivee') is None:
            data['heure_arrivee'] = None
            
        print("Data after validation:", data)
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
