# gym_project/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Toutes les routes de ton API (y compris JWT, ViewSets, etc.)
    path('api/', include('core.urls')),
]

# Pour le développement : servir les fichiers media (images, etc.)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
