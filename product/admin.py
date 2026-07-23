from django.contrib import admin
from .models import OnamSaree, OnamSareeImage
from .models import ColoredSaree, ColoredSareeImage


class OnamSareeImageInline(admin.TabularInline):
    model = OnamSareeImage
    extra = 1


@admin.register(OnamSaree)
class OnamSareeAdmin(admin.ModelAdmin):
    list_display = ('collection_name', 'price')
    search_fields = ('collection_name',)
    inlines = [OnamSareeImageInline]


@admin.register(OnamSareeImage)
class OnamSareeImageAdmin(admin.ModelAdmin):
    list_display = ('saree', 'image')


class ColoredSareeImageInline(admin.TabularInline):
    model = ColoredSareeImage
    extra = 1


@admin.register(ColoredSaree)
class ColoredSareeAdmin(admin.ModelAdmin):
    list_display = ('collection_name', 'price')
    search_fields = ('collection_name',)
    inlines = [ColoredSareeImageInline]


@admin.register(ColoredSareeImage)
class ColoredSareeImageAdmin(admin.ModelAdmin):
    list_display = ('saree', 'image')
