from django.contrib import admin
from .models import Category, Product, ProductVariant, ProductImage

# --- INLINES (Para ver Variantes y Fotos dentro del Producto) ---

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    # Django renderiza el JSONField como un textarea por defecto, lo cual sirve.

# --- ADMINS PRINCIPALES ---

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # Fusioné tus dos configuraciones aquí:
    list_display = ['name', 'category', 'is_active', 'is_featured', 'featured_order', 'updated_at']
    list_filter = ['is_active', 'is_featured', 'category']
    search_fields = ['name', 'slug']
    
    # Esto autocompleta el slug mientras escribes el nombre
    prepopulated_fields = {'slug': ('name',)} 
    
    # Organizar campos en secciones
    fieldsets = (
        ('Básico', {
            'fields': ('name', 'slug', 'category', 'description')
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Featured (Home)', {
            'fields': ('is_featured', 'featured_order'),
            'description': 'Marca is_featured=True para mostrar en home. featured_order define el orden visual (1-4).'
        }),
        ('SEO', {
            'fields': ('seo_title', 'seo_description')
        }),
    )
    
    # Esto muestra las variantes y fotos abajo
    inlines = [ProductVariantInline, ProductImageInline] 

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'price', 'stock', 'is_default']
    list_filter = ['product']
    search_fields = ['sku']

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'variant', 'is_cover']