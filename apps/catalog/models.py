from django.db import models
from django.utils.text import slugify


class ActiveProductManager(models.Manager):
    """Manager para obtener solo productos activos"""
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True, db_index=True) # Blank permite que se genere auto en save()
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    image_url = models.URLField(max_length=500, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=['parent'], name='idx_category_parent'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        full_path = [self.name]
        k = self.parent
        while k is not None:
            full_path.append(k.name)
            k = k.parent
        return ' -> '.join(full_path[::-1])

    def get_descendants(self):
        """Devuelve esta categoría y todas sus subcategorías descendientes"""
        descendants = [self]
        for child in self.children.all():
            descendants.extend(child.get_descendants())
        return descendants

class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Managers
    objects = models.Manager()  # Manager por defecto (incluye todos)
    active = ActiveProductManager()  # Manager para productos activos
    
    # Featured Products
    is_featured = models.BooleanField(default=False, help_text="Mostrar en home")
    featured_order = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Orden visual (1-4)")
    
    # SEO
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'created_at'], name='idx_product_active_created'),
            models.Index(fields=['is_active', 'category'], name='idx_product_active_category'),
            models.Index(fields=['is_active', 'is_featured'], name='idx_product_active_featured'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    
    # EL CORAZÓN DE TU SISTEMA GENÉRICO:
    attributes = models.JSONField(default=dict, help_text='Ej: {"talle": "L", "color": "Rojo"}')
    
    weight = models.DecimalField(max_digits=6, decimal_places=3, default=0.100, help_text="Peso en KG")
    length = models.DecimalField(max_digits=5, decimal_places=1, default=10.0, help_text="Largo en CM")
    width = models.DecimalField(max_digits=5, decimal_places=1, default=10.0, help_text="Ancho en CM")
    height = models.DecimalField(max_digits=5, decimal_places=1, default=5.0, help_text="Alto en CM")

    is_default = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'price'], name='idx_variant_product_price'),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.sku})"

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, related_name='variant_images', null=True, blank=True, on_delete=models.SET_NULL)
    
    # Usamos ImageField. Requiere 'pip install Pillow'
    # upload_to organizará las carpetas por año/mes
    image = models.ImageField(upload_to='products/%Y/%m/') 
    image_url = models.URLField(blank=True, null=True, help_text="Opcional si usas CDN externo en vez de subir archivo")
    
    alt_text = models.CharField(max_length=255, blank=True)
    is_cover = models.BooleanField(default=False)

    def __str__(self):
        return f"Img for {self.product.name}"