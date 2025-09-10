# figma 추가 dashboard
from django.urls import path
from .views import shortest_path_view, esp_event_view, dashboard_text, floor1_page, dashboard_page
from django.views.generic import RedirectView

urlpatterns = [
    path('shortest-path/', shortest_path_view, name='shortest-path'),
    path('esp-event/', esp_event_view, name='esp-event'),
    path('dashboard.txt', dashboard_text, name='dashboard-text'),
    path('dashboard.txt/', dashboard_text),  # 슬래시 실수 대응

    path('floor1/', floor1_page, name='floor1-page'),
    path('dashboard/', dashboard_page, name='dashboard-page'),
]