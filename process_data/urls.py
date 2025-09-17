from django.urls import path
from .views import AnesthesiaCalculationAPIView

app_name = 'process_data'

urlpatterns = [
    path('anesthesia-calculation/', AnesthesiaCalculationAPIView.as_view(),
         name='anesthesia_calculation'),
]
