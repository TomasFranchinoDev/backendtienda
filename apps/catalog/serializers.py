from rest_framework import serializers
from .models import Category, Product, ProductVariant, ProductImage

class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    parent_id = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image_url', 'parent_id', 'children']

    def get_children(self, obj):
        try:
        # Use prefetched data
            children = obj._prefetched_objects_cache.get('children', [])
            if children:
                return CategorySerializer(children, many=True).data
            return []
        except AttributeError:
            return []

    def get_parent_id(self, obj):
        return obj.parent_id

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'image_url', 'alt_text', 'is_cover']

class ProductVariantSerializer(serializers.ModelSerializer):
    # DRF maneja el campo JSON 'attributes' automáticamente como un objeto.
    class Meta:
        model = ProductVariant
        fields = ['id', 'sku', 'price', 'stock', 'attributes', 'is_default']



# SERIALIZER LIGERO (Para listados)
class ProductListSerializer(serializers.ModelSerializer):
    price_start = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    has_variants = serializers.SerializerMethodField()
    category = serializers.StringRelatedField() # Muestra el nombre en vez del ID

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'category', 'price_start', 'thumbnail', 'has_variants']

    def get_price_start(self, obj):
        # Devuelve el precio más bajo encontrado entre las variantes
        # ✅ BIEN: obj.variants.all() usa la caché del prefetch_related
        variants = obj.variants.all()
        
        if not variants:
            return None
            
        # Calculamos el precio más bajo usando Python (RAM)
        # Esto es instantáneo para <100 variantes y ahorra 20 queries por página
        return min(v.price for v in variants)

    def get_has_variants(self, obj):
        return obj.variants.exists()

    def get_thumbnail(self, obj):
        images = getattr(obj, 'images', None)
        if not images:
            return None

        images_list = list(images.all())
        if not images_list:
            return None

        cover = next((img for img in images_list if img.is_cover), None)
        image = cover or images_list[0]

        return image.image.url

# SERIALIZER COMPLETO (Para detalle de producto)
class ProductDetailSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    price_start = serializers.SerializerMethodField()
    has_variants = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 
            'category', 'seo_title', 'seo_description',
            'variants', 'images', 'price_start', 'has_variants'
        ]

    def get_price_start(self, obj):
        variants = obj.variants.all()
        if variants.exists():
            return min([v.price for v in variants])
        return None

    def get_has_variants(self, obj):
        return obj.variants.exists()