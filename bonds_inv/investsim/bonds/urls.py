from django.urls import path
from .views import InvestmentSimulationView, DownloadExcelView

urlpatterns = [
    path('simulate/', InvestmentSimulationView.as_view()),
    path('simulate/download/', DownloadExcelView.as_view())
]
