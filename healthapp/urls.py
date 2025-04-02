from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('chat', views.chat, name='chat'),
    path('generate_workout', views.generate_workout, name='generate_workout'),
    path('track_diet', views.track_diet, name='track_diet'),
] 