from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from .forms import OnamSareeForm, OnamSetMundForm, ColoredSareeForm
from .models import OnamSaree, OnamSareeImage, OnamSetMund, OnamSetMundImage, ColoredSaree, ColoredSareeImage

# Create your views here.
def home(request):
    sarees = OnamSaree.objects.prefetch_related('images').all()[:6]
    munds = OnamSetMund.objects.prefetch_related('images').all()[:6]
    colored = ColoredSaree.objects.prefetch_related('images').all()[:6]
    return render(request, 'product/home.html', {'sarees': sarees, 'munds': munds, 'colored': colored})


def admin_dashboard(request):
    return render(request, 'admin/admin.html')


def add_onam_set_mund(request):
    if request.method == 'POST':
        form = OnamSetMundForm(request.POST, request.FILES)
        if form.is_valid():
            mund = form.save(commit=False)
            mund.stock_available = request.POST.get('stock_available') == 'on'
            mund.quantity = int(request.POST.get('quantity', 0))
            mund.save()

            images = request.FILES.getlist('images')
            for image in images:
                OnamSetMundImage.objects.create(mund=mund, image=image)

            return redirect('list_onam_set_munds')
    else:
        form = OnamSetMundForm()

    return render(request, 'product/add_onam_set_mund.html', {'form': form})


# def add_onam_saree(request):
#     if request.method == 'POST':
#         form = OnamSareeForm(request.POST, request.FILES)
#         if form.is_valid():
#             saree = form.save(commit=False)
#             saree.save()

#             images = request.FILES.getlist('images')
#             for image in images:
#                 OnamSareeImage.objects.create(saree=saree, image=image)

#             return redirect('admin_dashboard')
#     else:
#         form = OnamSareeForm()

#     return render(request, 'product/add_onam_saree.html', {'form': form})


def add_onam_saree(request):
    if request.method == 'POST':
        form = OnamSareeForm(request.POST, request.FILES)

        if form.is_valid():
            print("FILES:", request.FILES)

            saree = form.save(commit=False)
            saree.save()

            images = request.FILES.getlist("images")
            print("Images count:", len(images))

            for image in images:
                print("Uploading:", image.name)

                obj = OnamSareeImage(saree=saree)
                obj.image = image
                obj.save()

                print("Uploaded:", obj.image.url)

            return redirect("admin_dashboard")

    else:
        form = OnamSareeForm()

    return render(request, "product/add_onam_saree.html", {"form": form})


def add_colored_saree(request):
    if request.method == 'POST':
        form = ColoredSareeForm(request.POST, request.FILES)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                ColoredSareeImage.objects.create(saree=saree, image=image)

            return redirect('admin_dashboard')
    else:
        form = ColoredSareeForm()

    return render(request, 'product/add_colored_saree.html', {'form': form})


def list_onam_sarees(request):
    sarees = OnamSaree.objects.prefetch_related('images').all()
    return render(request, 'admin/list_onam_sarees.html', {'sarees': sarees})


def list_colored_sarees(request):
    sarees = ColoredSaree.objects.prefetch_related('images').all()
    return render(request, 'admin/list_colored_sarees.html', {'sarees': sarees})


def list_onam_set_munds(request):
    munds = OnamSetMund.objects.prefetch_related('images').all()
    return render(request, 'admin/list_onam_set_munds.html', {'munds': munds})


def edit_onam_saree(request, pk):
    saree = get_object_or_404(OnamSaree, pk=pk)
    if request.method == 'POST':
        form = OnamSareeForm(request.POST, request.FILES, instance=saree)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.stock_available = request.POST.get('stock_available') == 'on'
            saree.quantity = int(request.POST.get('quantity', 0))
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                OnamSareeImage.objects.create(saree=saree, image=image)

            return redirect('list_onam_sarees')
    else:
        form = OnamSareeForm(instance=saree)

    return render(request, 'admin/edit_onam_saree.html', {'form': form, 'saree': saree})


def edit_colored_saree(request, pk):
    saree = get_object_or_404(ColoredSaree, pk=pk)
    if request.method == 'POST':
        form = ColoredSareeForm(request.POST, request.FILES, instance=saree)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.stock_available = request.POST.get('stock_available') == 'on'
            saree.quantity = int(request.POST.get('quantity', 0))
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                ColoredSareeImage.objects.create(saree=saree, image=image)

            return redirect('list_colored_sarees')
    else:
        form = ColoredSareeForm(instance=saree)

    return render(request, 'admin/edit_colored_saree.html', {'form': form, 'saree': saree})


def delete_onam_saree(request, pk):
    saree = get_object_or_404(OnamSaree, pk=pk)
    if request.method == 'POST':
        saree.delete()
    return redirect('list_onam_sarees')


def delete_colored_saree(request, pk):
    saree = get_object_or_404(ColoredSaree, pk=pk)
    if request.method == 'POST':
        saree.delete()
    return redirect('list_colored_sarees')


def edit_onam_set_mund(request, pk):
    mund = get_object_or_404(OnamSetMund, pk=pk)
    if request.method == 'POST':
        form = OnamSetMundForm(request.POST, request.FILES, instance=mund)
        if form.is_valid():
            mund = form.save(commit=False)
            mund.stock_available = request.POST.get('stock_available') == 'on'
            mund.quantity = int(request.POST.get('quantity', 0))
            mund.save()

            images = request.FILES.getlist('images')
            for image in images:
                OnamSetMundImage.objects.create(mund=mund, image=image)

            return redirect('list_onam_set_munds')
    else:
        form = OnamSetMundForm(instance=mund)

    return render(request, 'admin/edit_onam_set_mund.html', {'form': form, 'mund': mund})


def delete_onam_set_mund(request, pk):
    mund = get_object_or_404(OnamSetMund, pk=pk)
    if request.method == 'POST':
        mund.delete()
    return redirect('list_onam_set_munds')


def onam_saree_explore(request):
    sarees = OnamSaree.objects.prefetch_related('images').all()
    return render(request, 'product/onam_saree_explore.html', {'sarees': sarees})


def colored_saree_explore(request):
    sarees = ColoredSaree.objects.prefetch_related('images').all()
    return render(request, 'product/colored_saree_explore.html', {'sarees': sarees})


def onam_mund_explore(request):
    munds = OnamSetMund.objects.prefetch_related('images').all()
    return render(request, 'product/onam_mund_explore.html', {'munds': munds})


PRODUCT_MODEL_BY_TYPE = {
    'saree': OnamSaree,
    'mund': OnamSetMund,
    'colored': ColoredSaree,
}


def product_modal(request, product_type, pk):
    model = PRODUCT_MODEL_BY_TYPE.get(product_type)
    if model is None:
        raise Http404('Unknown product type')

    product = get_object_or_404(model, pk=pk)
    return render(request, 'product/_product_modal.html', {
        'product': product,
        'images': product.images.all(),
        'product_type': product_type,
    })


