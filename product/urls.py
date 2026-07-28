from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/add-onam-saree/', views.add_onam_saree, name='add_onam_saree'),
    path('admin-panel/add-onam-set-mund/', views.add_onam_set_mund, name='add_onam_set_mund'),
    path('admin-panel/list-onam-sarees/', views.list_onam_sarees, name='list_onam_sarees'),
    path('admin-panel/list-onam-set-munds/', views.list_onam_set_munds, name='list_onam_set_munds'),
    path('admin-panel/edit-onam-saree/<int:pk>/', views.edit_onam_saree, name='edit_onam_saree'),
    path('admin-panel/delete-onam-saree/<int:pk>/', views.delete_onam_saree, name='delete_onam_saree'),
    path('admin-panel/edit-onam-set-mund/<int:pk>/', views.edit_onam_set_mund, name='edit_onam_set_mund'),
    path('admin-panel/delete-onam-set-mund/<int:pk>/', views.delete_onam_set_mund, name='delete_onam_set_mund'),
    path('modal/<str:product_type>/<int:pk>/', views.product_modal, name='product_modal'),
    path('explore-onam/', views.onam_saree_explore, name='onam_saree_explore'),
    path('explore-colored-sarees/', views.colored_saree_explore, name='colored_saree_explore'),
    path('explore-onam-mund/', views.onam_mund_explore, name='onam_mund_explore'),
    path('admin-panel/add-colored-saree/', views.add_colored_saree, name='add_colored_saree'),
    path('admin-panel/list-colored-sarees/', views.list_colored_sarees, name='list_colored_sarees'),
    path('admin-panel/edit-colored-saree/<int:pk>/', views.edit_colored_saree, name='edit_colored_saree'),
    path('admin-panel/delete-colored-saree/<int:pk>/', views.delete_colored_saree, name='delete_colored_saree'),
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('admin-panel/users/', views.list_users, name='list_users'),
    path('admin-panel/users/edit/<int:pk>/', views.edit_user, name='edit_user'),
    path('admin-panel/users/delete/<int:pk>/', views.delete_user, name='delete_user'),
]
