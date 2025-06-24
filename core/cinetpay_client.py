from cinetpay import Client, Config, Credential
from django.conf import settings

credentials = Credential(
    apikey=settings.CINETPAY_APIKEY,
    site_id=settings.CINETPAY_SITEID
)

config = Config(
    credentials=credentials,
    lock_phone_number=True,  # ✅ CORRECT : 'lock_phone_number' au lieu de 'lock_phone'
    currency='XOF',  # ou XAF selon ton pays
    language='fr',  # ✅ CORRECT : 'language' au lieu de 'lang'
    notify_url='https://127.0.0.1:8000/api/cinetpay/notify/',
    return_url='https://127.0.0.1:8000/paiement/success/',
    channels='ALL',
    version='V1',
    raise_on_error=False  # ✅ requis par le SDK   
)

cinetpay_client = Client(configs=config)
