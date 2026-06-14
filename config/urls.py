from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from stands import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', views.stand_list, name='stand_list'),
    path('map/', views.stand_map, name='stand_map'),
    path('stand/<slug:slug>/', views.stand_detail, name='stand_detail'),
    path('stand/<slug:slug>/report/', views.stand_report, name='stand_report'),
    path('claim/<str:token>/', views.stand_claim, name='stand_claim'),
    path('my/', views.my_stands, name='my_stands'),
    path('my/<slug:slug>/today/', views.set_today, name='set_today'),
    path('my/<slug:slug>/edit/', views.edit_stand, name='edit_stand'),
    path('my/<slug:slug>/hours/', views.edit_hours, name='edit_hours'),
    path('my/<slug:slug>/pin/', views.edit_pin, name='edit_pin'),
    path('my/<slug:slug>/photos/', views.stand_photos, name='stand_photos'),
    path('my/<slug:slug>/photos/<int:pk>/delete/', views.delete_photo,
         name='delete_photo'),
    path('my/<slug:slug>/photos/<int:pk>/make-thumb/', views.set_list_photo,
         name='set_list_photo'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Whitenoise only serves static files; owner-uploaded media is served
    # by Django itself. Fine at this scale (a handful of photos, Cloudflare
    # caches in front), and avoids adding nginx to the 1 GB box.
    from django.urls import re_path
    from django.views.static import serve as media_serve
    urlpatterns += [re_path(r'^media/(?P<path>.*)$', media_serve,
                            {'document_root': settings.MEDIA_ROOT})]
