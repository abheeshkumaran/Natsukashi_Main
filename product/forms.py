from django import forms
from .models import Product, Category, UpdationTask

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category Name'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
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
        fields = ['collection_name', 'description', 'price', 'quantity', 'stock_available']
        widgets = {
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
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
