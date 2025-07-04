from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from django.core.files.base import ContentFile
from io import BytesIO
import uuid

def generer_facture_pdf(obj, paiement, type_ticket='SEANCE'):
    """
    Génère un PDF stylé pour une facture ou un ticket.
    obj : Seance, Reservation, AbonnementClient, AbonnementClientPresentiel, etc.
    paiement : instance de Paiement liée (peut être None pour les abonnements présentiels)
    type_ticket : 'SEANCE' ou 'ABONNEMENT'
    Retourne un ContentFile prêt à être sauvegardé dans un FileField.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    styleN = styles['Normal']
    styleH = styles['Heading1']
    styleH.alignment = 1  # centré
    styleTitle = ParagraphStyle('title', parent=styles['Heading1'], fontSize=28, textColor=colors.HexColor('#215BAA'), alignment=1, spaceAfter=10)
    styleSub = ParagraphStyle('subtitle', parent=styles['Heading2'], fontSize=16, alignment=1, spaceAfter=18)
    styleTableHeader = ParagraphStyle('tableheader', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#215BAA'), alignment=0, spaceAfter=0, spaceBefore=0)
    styleTableCell = ParagraphStyle('tablecell', parent=styles['Normal'], fontSize=12, alignment=0, spaceAfter=0, spaceBefore=0)

    # En-tête
    elements.append(Paragraph("GYMZONE", styleTitle))
    if type_ticket == 'ABONNEMENT':
        elements.append(Paragraph(f"Facture Abonnement", styleSub))
    else:
        elements.append(Paragraph(f"Ticket Séance", styleSub))
    elements.append(Spacer(1, 12))

    # Préparation des infos selon le type d'objet
    if type_ticket == 'ABONNEMENT' and hasattr(obj, 'montant_total'):
        # Cas d'un AbonnementClientPresentiel
        client_nom = obj.client_nom or ""
        client_prenom = obj.client_prenom or ""
        date_debut = obj.date_debut.strftime('%d/%m/%Y') if hasattr(obj.date_debut, 'strftime') else str(obj.date_debut)
        date_fin = obj.date_fin.strftime('%d/%m/%Y') if hasattr(obj.date_fin, 'strftime') else str(obj.date_fin)
        montant = obj.montant_total
        montant_paye = obj.montant_paye
        abonnement_nom = getattr(obj, 'abonnement_nom', '') or (obj.abonnement.nom if hasattr(obj, 'abonnement') else '')
        
        # Tableau des infos pour abonnement
        data = [
            [Paragraph('<b>Nom du client</b>', styleTableHeader), Paragraph(f"{client_prenom} {client_nom}", styleTableCell)],
            [Paragraph('<b>Type d\'abonnement</b>', styleTableHeader), Paragraph(abonnement_nom, styleTableCell)],
            [Paragraph('<b>Date de début</b>', styleTableHeader), Paragraph(date_debut, styleTableCell)],
            [Paragraph('<b>Date de fin</b>', styleTableHeader), Paragraph(date_fin, styleTableCell)],
            [Paragraph('<b>Montant total</b>', styleTableHeader), Paragraph(f"{montant} FCFA", styleTableCell)],
            [Paragraph('<b>Montant payé</b>', styleTableHeader), Paragraph(f"{montant_paye} FCFA", styleTableCell)],
            [Paragraph('<b>Date d\'émission</b>', styleTableHeader), Paragraph(obj.date_creation.strftime('%d/%m/%Y') if hasattr(obj.date_creation, 'strftime') else str(obj.date_creation), styleTableCell)],
            [Paragraph('<b>Référence</b>', styleTableHeader), Paragraph(str(obj.id), styleTableCell)],
        ]
        
        # Total pour abonnement
        total_text = f"<b>Total payé : <font color='#215BAA'>{montant_paye} FCFA</font></b>"
        if montant_paye < montant:
            total_text += f"<br/><font color='#FF6B6B'>Reste à payer : {montant - montant_paye} FCFA</font>"
            
    else:
        # Cas d'une séance ou autre
        if hasattr(obj, 'client_nom') and hasattr(obj, 'client_prenom'):
            client_nom = obj.client_nom or ""
            client_prenom = obj.client_prenom or ""
            date_info = getattr(obj, 'date_jour', '') or ""
            heures_info = getattr(obj, 'nombre_heures', 0) or 0
        elif hasattr(obj, 'client') and hasattr(obj, 'date_heure_souhaitee'):
            client_nom = obj.client.nom if hasattr(obj.client, 'nom') else ""
            client_prenom = obj.client.prenom if hasattr(obj.client, 'prenom') else ""
            date_info = obj.date_heure_souhaitee.strftime('%d/%m/%Y %H:%M') if obj.date_heure_souhaitee else ""
            heures_info = obj.nombre_heures or 0
        else:
            client_nom = getattr(obj, 'client_nom', '') or (getattr(obj, 'client', {}).nom if hasattr(obj, 'client') else '')
            client_prenom = getattr(obj, 'client_prenom', '') or (getattr(obj, 'client', {}).prenom if hasattr(obj, 'client') else '')
            date_info = getattr(obj, 'date_jour', '') or getattr(obj, 'date_heure_souhaitee', '')
            heures_info = getattr(obj, 'nombre_heures', 0) or 0

        # Tableau des infos pour séance
        data = [
            [Paragraph('<b>Nom du client</b>', styleTableHeader), Paragraph(f"{client_prenom} {client_nom}", styleTableCell)],
            [Paragraph('<b>Date séance</b>', styleTableHeader), Paragraph(str(date_info), styleTableCell)],
            [Paragraph('<b>Nombre d\'heures</b>', styleTableHeader), Paragraph(str(heures_info), styleTableCell)],
            [Paragraph('<b>Montant payé</b>', styleTableHeader), Paragraph(f"{paiement.montant} FCFA", styleTableCell)],
            [Paragraph('<b>Date d\'émission</b>', styleTableHeader), Paragraph(paiement.date_paiement.strftime('%d/%m/%Y'), styleTableCell)],
            [Paragraph('<b>Référence paiement</b>', styleTableHeader), Paragraph(str(paiement.id), styleTableCell)],
        ]
        
        # Total pour séance
        total_text = f"<b>Total à payer : <font color='#215BAA'>{paiement.montant} FCFA</font></b>"

    table = Table(data, colWidths=[120, 260])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EAF1FB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#215BAA')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F8FB')]),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#215BAA')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#B0C4DE')),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 30))

    # Total (bien visible)
    elements.append(Paragraph(total_text, ParagraphStyle('total', fontSize=15, alignment=2, spaceAfter=18)))

    # Message de remerciement
    elements.append(Spacer(1, 18))
    elements.append(Paragraph("Merci pour votre confiance chez <b>GYMZONE</b> !", ParagraphStyle('thanks', fontSize=12, alignment=1, textColor=colors.HexColor('#215BAA'))))

    doc.build(elements)
    pdf_content = buffer.getvalue()
    buffer.close()
    filename = f"{type_ticket.lower()}_{uuid.uuid4()}.pdf"
    return ContentFile(pdf_content, name=filename) 