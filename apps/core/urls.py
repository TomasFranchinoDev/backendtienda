from django.urls import path

from .views import ShopConfigView

urlpatterns = [
    path('config/', ShopConfigView.as_view(), name='shop-config'),
]
