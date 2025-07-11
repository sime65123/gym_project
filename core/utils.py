from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from django.core.files.base import ContentFile
from django.conf import settings
import os
from io import BytesIO
import uuid

def generer_facture_pdf(obj, paiement, type_ticket='SEANCE'):
    """
    Génère un PDF stylé pour un ticket de réservation.
    obj : Reservation, Seance, AbonnementClient, etc.
    paiement : instance de Paiement liée
    type_ticket : 'SEANCE' ou 'ABONNEMENT'
    Retourne un ContentFile prêt à être sauvegardé dans un FileField.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    
    # Styles personnalisés
    styleTitle = ParagraphStyle('title', parent=styles['Heading1'], fontSize=32, textColor=colors.HexColor('#215BAA'), alignment=1, spaceAfter=20)
    styleSubtitle = ParagraphStyle('subtitle', parent=styles['Heading2'], fontSize=18, textColor=colors.HexColor('#4A90E2'), alignment=1, spaceAfter=15)
    styleSuccess = ParagraphStyle('success', parent=styles['Normal'], fontSize=16, textColor=colors.HexColor('#28A745'), alignment=1, spaceAfter=20)
    styleInfo = ParagraphStyle('info', parent=styles['Normal'], fontSize=14, textColor=colors.HexColor('#6C757D'), alignment=0, spaceAfter=8, leftIndent=20)
    styleHighlight = ParagraphStyle('highlight', parent=styles['Normal'], fontSize=16, textColor=colors.HexColor('#215BAA'), alignment=0, spaceAfter=10, leftIndent=20)
    styleAmount = ParagraphStyle('amount', parent=styles['Heading2'], fontSize=20, textColor=colors.HexColor('#DC3545'), alignment=1, spaceAfter=25)
    styleFooter = ParagraphStyle('footer', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#6C757D'), alignment=1, spaceAfter=10)

    # Logo GYMZONE (si le fichier existe)
    logo_path = os.path.join(settings.BASE_DIR, 'gym-management-app', 'public', 'lg1.jpg')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=80, height=80)
            logo.hAlign = 'CENTER'
            elements.append(logo)
            elements.append(Spacer(1, 10))
        except:
            pass
    
    # En-tête avec logo (texte stylé comme logo)
    elements.append(Paragraph("🏋️ GYMZONE", styleTitle))
    elements.append(Spacer(1, 10))
    
    # Message de réservation réussie
    elements.append(Paragraph("✅ RÉSERVATION RÉUSSIE", styleSuccess))
    elements.append(Spacer(1, 15))
    
    # Message principal
    elements.append(Paragraph("Passez à la salle pour effectuer votre paiement", styleSubtitle))
    elements.append(Spacer(1, 25))

    # Informations de la réservation
    if hasattr(obj, 'nom_client'):
        # Cas d'une réservation
        client_nom = obj.nom_client
        type_reservation = obj.type_reservation
        montant = obj.montant
        description = obj.description or ""
        date_creation = obj.id  # Utiliser l'ID comme référence
        
        elements.append(Paragraph(f"<b>👤 Client :</b> {client_nom}", styleHighlight))
        elements.append(Paragraph(f"<b>🎯 Type :</b> {type_reservation}", styleHighlight))
        
        # Afficher "À définir" pour les réservations de séance en attente
        if type_reservation == 'SEANCE' and montant == 0 and paiement and paiement.montant > 0:
            # Si la séance a été validée et qu'un paiement existe, afficher le montant payé
            elements.append(Paragraph(f"<b>💰 Montant :</b> {paiement.montant} FCFA", styleHighlight))
        elif type_reservation == 'SEANCE' and montant == 0:
            elements.append(Paragraph(f"<b>💰 Montant :</b> À définir par l'employé", styleHighlight))
        else:
            elements.append(Paragraph(f"<b>💰 Montant :</b> {montant} FCFA", styleHighlight))
            
        if description:
            elements.append(Paragraph(f"<b>📝 Description :</b> {description}", styleHighlight))
        elements.append(Paragraph(f"<b>🔢 Référence :</b> #{date_creation}", styleHighlight))
        
    elif type_ticket == 'ABONNEMENT' and hasattr(obj, 'montant_total'):
        # Cas d'un abonnement présentiel
        client_nom = f"{obj.client_prenom} {obj.client_nom}"
        abonnement_nom = obj.abonnement.nom if hasattr(obj, 'abonnement') else "Abonnement"
        montant = obj.montant_total
        date_debut = obj.date_debut.strftime('%d/%m/%Y') if hasattr(obj.date_debut, 'strftime') else str(obj.date_debut)
        date_fin = obj.date_fin.strftime('%d/%m/%Y') if hasattr(obj.date_fin, 'strftime') else str(obj.date_fin)
        
        elements.append(Paragraph(f"<b>👤 Client :</b> {client_nom}", styleHighlight))
        elements.append(Paragraph(f"<b>🎯 Type :</b> Abonnement {abonnement_nom}", styleHighlight))
        elements.append(Paragraph(f"<b>💰 Montant :</b> {montant} FCFA", styleHighlight))
        elements.append(Paragraph(f"<b>📅 Période :</b> {date_debut} au {date_fin}", styleHighlight))
        elements.append(Paragraph(f"<b>🔢 Référence :</b> #{obj.id}", styleHighlight))
            
    else:
        # Cas d'une séance
        if hasattr(obj, 'client_nom') and hasattr(obj, 'client_prenom'):
            client_nom = f"{obj.client_prenom} {obj.client_nom}"
        else:
            client_nom = "Client"
            
        montant = paiement.montant if paiement else 0
        date_info = getattr(obj, 'date_jour', '') or ""
        heures_info = getattr(obj, 'nombre_heures', 0) or 0
        
        elements.append(Paragraph(f"<b>👤 Client :</b> {client_nom}", styleHighlight))
        elements.append(Paragraph(f"<b>🎯 Type :</b> Séance d'entraînement", styleHighlight))
        elements.append(Paragraph(f"<b>💰 Montant :</b> {montant} FCFA", styleHighlight))
        if date_info:
            elements.append(Paragraph(f"<b>📅 Date :</b> {date_info}", styleHighlight))
        if heures_info:
            elements.append(Paragraph(f"<b>⏱️ Durée :</b> {heures_info} heure(s)", styleHighlight))
        elements.append(Paragraph(f"<b>🔢 Référence :</b> #{obj.id}", styleHighlight))

    elements.append(Spacer(1, 30))
    
    # Montant en évidence
    montant_total = obj.montant if hasattr(obj, 'montant') else (paiement.montant if paiement else 0)
    
    # Afficher "À définir" pour les réservations de séance en attente
    if hasattr(obj, 'type_reservation') and obj.type_reservation == 'SEANCE' and montant_total == 0 and paiement and paiement.montant > 0:
        elements.append(Paragraph(f"<b>💳 MONTANT À PAYER : {paiement.montant} FCFA</b>", styleAmount))
    elif hasattr(obj, 'type_reservation') and obj.type_reservation == 'SEANCE' and montant_total == 0:
        elements.append(Paragraph(f"<b>💳 MONTANT À PAYER : À DÉFINIR</b>", styleAmount))
    else:
        elements.append(Paragraph(f"<b>💳 MONTANT À PAYER : {montant_total} FCFA</b>", styleAmount))
    
    elements.append(Spacer(1, 30))

    # Instructions importantes
    elements.append(Paragraph("📋 INSTRUCTIONS :", styleHighlight))
    
    # Instructions spécifiques selon le type
    if hasattr(obj, 'type_reservation') and obj.type_reservation == 'SEANCE' and montant_total == 0:
        # Réservation de séance en attente
        elements.append(Paragraph("• Présentez ce ticket à la réception", styleInfo))
        elements.append(Paragraph("• L'employé définira le montant selon vos besoins", styleInfo))
        elements.append(Paragraph("• Effectuez le paiement après validation", styleInfo))
        elements.append(Paragraph("• Votre séance sera confirmée après paiement", styleInfo))
    else:
        # Réservation confirmée ou abonnement
        elements.append(Paragraph("• Présentez ce ticket à la réception", styleInfo))
        elements.append(Paragraph("• Effectuez le paiement en espèces ou par carte", styleInfo))
        elements.append(Paragraph("• Conservez votre reçu de paiement", styleInfo))
        elements.append(Paragraph("• Votre réservation sera confirmée après paiement", styleInfo))
    
    elements.append(Spacer(1, 30))

    # Message de remerciement
    elements.append(Paragraph("🏆 Merci pour votre confiance chez GYMZONE !", styleFooter))
    elements.append(Paragraph("💪 Votre bien-être est notre priorité", styleFooter))

    doc.build(elements)
    pdf_content = buffer.getvalue()
    buffer.close()
    filename = f"ticket_{type_ticket.lower()}_{uuid.uuid4()}.pdf"
    return ContentFile(pdf_content, name=filename) 