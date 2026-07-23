from django import forms
from .models import OnamSaree, OnamSetMund

from .models import ColoredSaree


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        if name in files:
            return files.getlist(name)
        return None


class OnamSareeForm(forms.ModelForm):
    class Meta:
        model = OnamSaree
        fields = ['collection_name', 'description', 'price', 'quantity', 'stock_available']
        widgets = {
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'stock_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class OnamSetMundForm(forms.ModelForm):
    class Meta:
        model = OnamSetMund
        fields = ['collection_name', 'description', 'price', 'quantity', 'stock_available']
        widgets = {
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'stock_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ColoredSareeForm(forms.ModelForm):
    class Meta:
        model = ColoredSaree
        fields = ['collection_name', 'description', 'price', 'quantity', 'stock_available']
        widgets = {
            'collection_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Collection Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 4}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'stock_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
