from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import OuterRef, Subquery, DecimalField
from .models import Product, Category, ProductVariant
from .serializers import (
    ProductListSerializer, 
    ProductDetailSerializer, 
    CategorySerializer
)
from .filters import ProductFilter

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().prefetch_related('children')
    serializer_class = CategorySerializer
    lookup_field = 'slug' # Para buscar por /categories/ropa-hombre/
    pagination_class = None

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Listado y detalle de productos activos.
    Permite filtrar por:
    - Keywords: ?search=remera
    - Categoría: ?category=ropa
    - Precio: ?min_price=100&max_price=500
    """
    queryset = Product.objects.filter(is_active=True)
    lookup_field = 'slug'
    
    # Configuración de filtros
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'name', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        # Subquery: obtiene el precio mínimo de cada producto sin JOINs ni duplicados
        min_price_subquery = ProductVariant.objects.filter(
            product=OuterRef('pk')
        ).order_by('price').values('price')[:1]

        return Product.objects.filter(
            is_active=True
        ).annotate(
            price=Subquery(min_price_subquery, output_field=DecimalField())
        ).select_related('category').prefetch_related('images', 'variants')
    
    def filter_queryset(self, queryset):
        """Sobrescribir para forzar filtro is_active=True en todos los casos"""
        queryset = super().filter_queryset(queryset)
        # Forzar el filtro is_active=True por si acaso
        return queryset.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=['get'])
    def featured(self, request):
        # Single query with conditional logic
        featured_products = Product.objects.filter(
            is_active=True, is_featured=True
        ).prefetch_related('images', 'variants').order_by('featured_order', '-created_at')[:4]
        
        if featured_products.count() < 4:
            extra_count = 4 - len(featured_products)
            featured_ids = [p.id for p in featured_products]
            extra = Product.objects.filter(
                is_active=True
            ).exclude(id__in=featured_ids).prefetch_related(
                'images', 'variants'
            ).order_by('-created_at')[:extra_count]
            featured_products = list(featured_products) + list(extra)
        
        serializer = ProductListSerializer(featured_products, many=True)
        return Response(serializer.data)