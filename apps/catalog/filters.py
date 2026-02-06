import django_filters
from django.db.models import Q 
from .models import Product, Category

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(method='filter_by_min_price')
    max_price = django_filters.NumberFilter(method='filter_by_max_price')
    category = django_filters.CharFilter(method='filter_by_category')

    class Meta:
        model = Product
        fields = ['category', 'min_price', 'max_price']

    def filter_by_min_price(self, queryset, name, value):
        """Filtra por precio mínimo usando la anotación 'price' del queryset"""
        return queryset.filter(price__gte=value)

    def filter_by_max_price(self, queryset, name, value):
        """Filtra por precio máximo usando la anotación 'price' del queryset"""
        return queryset.filter(price__lte=value)

    def filter_by_category(self, queryset, name, value):
        """
        Filtra productos por categoría, incluyendo subcategorías.
        Usa una sola query con category_id__in en vez de queries recursivas.
        """
        try:
            category = Category.objects.get(slug=value)
            
            # Recolectar todos los IDs de descendientes en una sola pasada
            descendant_ids = self._get_descendant_ids(category.id)
            
            return queryset.filter(category_id__in=descendant_ids)
            
        except Category.DoesNotExist:
            return queryset

    def _get_descendant_ids(self, category_id):
        """
        Obtiene IDs de categoría + descendientes con una sola query recursiva en Python.
        Usa Category.objects.values_list para traer todo de una vez.
        """
        # Traer TODAS las relaciones parent-child en una sola query
        all_categories = dict(
            Category.objects.values_list('id', 'parent_id')
        )
        
        # Construir mapa de hijos
        children_map = {}
        for cat_id, parent_id in all_categories.items():
            if parent_id is not None:
                children_map.setdefault(parent_id, []).append(cat_id)
        
        # BFS para encontrar todos los descendientes
        result = {category_id}
        queue = [category_id]
        while queue:
            current = queue.pop(0)
            for child_id in children_map.get(current, []):
                if child_id not in result:
                    result.add(child_id)
                    queue.append(child_id)
        
        return list(result)