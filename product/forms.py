from django import forms
from .models import Product, Category, UpdationTask, ProductCoupon, HeroSection

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category Name'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }


class HeroSectionForm(forms.ModelForm):
    class Meta:
        model = HeroSection
        fields = ['hero_content', 'hero_para_1', 'hero_para_2', 'marquee_text']
        widgets = {
            'hero_content': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Hero heading'}),
            'hero_para_1': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'First paragraph'}),
            'hero_para_2': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Second paragraph'}),
            'marquee_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Scrolling text shown under the navbar'}),
        }


class ProductCouponForm(forms.ModelForm):
    class Meta:
        model = ProductCoupon
        fields = [
            'coupon_code', 'coupon_name', 'discount_type', 'discount_value',
            'min_order_amount', 'min_qty', 'valid_from', 'valid_until', 'usage_limit', 'is_active',
        ]
        widgets = {
            'coupon_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SAREE20'}),
            'coupon_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Onam Special Discount'}),
            'discount_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_discount_type'}),
            'discount_value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Discount value', 'step': '0.01'}),
            'min_order_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Minimum order amount', 'step': '0.01'}),
            'min_qty': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Minimum product quantity'}),
            'valid_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'usage_limit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 = unlimited'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        if name in files:
            return files.getlist(name)
        return None

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['collection_name', 'description', 'fake_price', 'price', 'quantity', 'stock_available']
        widgets = {
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
            'fake_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Fake Price (MRP)', 'step': '0.01'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'stock_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class UpdationTaskForm(forms.ModelForm):
    class Meta:
        model = UpdationTask
        fields = ['issue_related', 'raised_by', 'related_image', 'description']
        widgets = {
            'issue_related': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Issue Related'}),
            'raised_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Raised By'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
        }
