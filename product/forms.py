from django import forms
from .models import Product

class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        if name in files:
            return files.getlist(name)
        return None

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['category', 'collection_name', 'description', 'price', 'quantity', 'stock_available']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'stock_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
