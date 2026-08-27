from django.contrib import admin
from .models import Category, Product, ProductImage, HeroSection

admin.site.register(HeroSection)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('collection_name', 'display_categories', 'price', 'quantity', 'stock_available')
    list_filter = ('categories', 'stock_available')
    
    def display_categories(self, obj):
        return ", ".join([category.name for category in obj.categories.all()])
    display_categories.short_description = 'Categories'
    search_fields = ('collection_name', 'description')
    inlines = [ProductImageInline]

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image')

