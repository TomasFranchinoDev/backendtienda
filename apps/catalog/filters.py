#import django_filters
#from .models import Product, Category

#class ProductFilter(django_filters.FilterSet):
 #   min_price = django_filters.NumberFilter(field_name="variants__price", lookup_expr='gte', distinct=True)
  #  max_price = django_filters.NumberFilter(field_name="variants__price", lookup_expr='lte', distinct=True)
   # category = django_filters.CharFilter(method='filter_by_category', distinct=True)

  #  class Meta:
   #     model = Product
    #    fields = ['category', 'min_price', 'max_price', 'is_active']
    
  #  @property
   # def qs(self):
    #    """Sobrescribir para forzar que siempre se filtren solo productos activos"""
     #   parent = super().qs
      #  return parent.filter(is_active=True)

#    def filter_by_category(self, queryset, name, value):
 #       """
  #      Filtra productos por categoría, incluyendo productos de todas sus subcategorías.
   #     Si se especifica una categoría padre, incluye productos de esa categoría y todas sus hijas.
    #    """
     #   try:
      #      category = Category.objects.get(slug=value)
       #     # Obtener la categoría y todos sus descendientes
        #    descendants = category.get_descendants()
         #   return queryset.filter(category__in=descendants)
     #   except Category.DoesNotExist:
      #      return queryset

import django_filters
from django.db.models import Q  # <--- 1. IMPORTANTE: Agrega esto arriba
from .models import Product, Category

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="variants__price", lookup_expr='gte', distinct=True)
    max_price = django_filters.NumberFilter(field_name="variants__price", lookup_expr='lte', distinct=True)
    category = django_filters.CharFilter(method='filter_by_category', distinct=True)

    class Meta:
        model = Product
        fields = ['category', 'min_price', 'max_price']

    def filter_by_category(self, queryset, name, value):
        """
        Filtra productos por categoría, incluyendo subcategorías.
        Solución compatible para librerías que no soportan include_self=True.
        """
        try:
            category = Category.objects.get(slug=value)
            
            # 1. Obtenemos los descendientes (sin pasar argumentos extra)
            descendants = category.get_descendants()
            
            # 2. Filtramos usando Q objects:
            # "El producto pertenece a la categoría buscada (category=category)"
            # "O ( | ) el producto pertenece a una de sus hijas (category__in=descendants)"
            return queryset.filter(
                Q(category=category) | Q(category__in=descendants)
            )
            
        except Category.DoesNotExist:
            return queryset