from xhtml2pdf import pisa
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from io import BytesIO
from .models import Paiement, Facture
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Paiement)
def create_facture_after_paiement(sender, instance, created, **kwargs):
    if instance.status == 'PAYE' and created:
        if not hasattr(instance, 'facture'):
            facture = Facture.objects.create(paiement=instance)
            html = render_to_string("facture_template.html", {
                "paiement": instance,
                "uuid": facture.uuid
            })
            output = BytesIO()
            pisa.CreatePDF(src=html, dest=output)
            filename = f"facture_{facture.uuid}.pdf"
            facture.fichier_pdf.save(filename, ContentFile(output.getvalue()))
            facture.save()
