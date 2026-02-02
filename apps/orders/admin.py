from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    # raw_id_fields reemplaza el dropdown gigante por una lupa de búsqueda.
    # Es mucho más rápido si tienes muchos productos.
    raw_id_fields = ('variant',) 
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'total', 'created_at']
    list_filter = ['status', 'created_at']
    
    # Buscador para encontrar órdenes por email de usuario o ID
    search_fields = ['id', 'user__email', 'user__username'] 
    
    inlines = [OrderItemInline]
    
    # Las fechas auto_now suelen dar error si no se ponen como readonly
    readonly_fields = ['created_at', 'updated_at']