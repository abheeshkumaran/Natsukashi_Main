from django.http import Http404, JsonResponse, HttpResponse
import csv
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .forms import OnamSareeForm, OnamSetMundForm, ColoredSareeForm
from .models import OnamSaree, OnamSareeImage, OnamSetMund, OnamSetMundImage, ColoredSaree, ColoredSareeImage, SiteUser, UserData, Order, OrderItem

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

def register_user(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        place = request.POST.get('place')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match!')
            return redirect(request.META.get('HTTP_REFERER', '/'))
            
        if SiteUser.objects.filter(email=email).exists():
            messages.error(request, 'Email is already registered!')
            return redirect(request.META.get('HTTP_REFERER', '/'))
            
        user = SiteUser(name=name, place=place, email=email, phone=phone)
        user.set_password(password)
        user.save()
        
        # Auto log in the user after registration
        request.session['site_user_id'] = user.id
        request.session['site_user_name'] = user.name
        
        messages.success(request, 'Account created successfully!')
        return redirect(request.META.get('HTTP_REFERER', '/'))
        
    return redirect('/')

def login_user(request):
    if request.method == 'POST':
        login_id = request.POST.get('email') # It comes from the name="email" input, but can be phone or email
        password = request.POST.get('password')
        try:
            user = SiteUser.objects.get(Q(email=login_id) | Q(phone=login_id))
            if user.check_password(password):
                request.session['site_user_id'] = user.id
                request.session['site_user_name'] = user.name
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'failed to login invalid password'})
        except SiteUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'failed to login invalid email or phone number'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def logout_user(request):
    request.session.pop('site_user_id', None)
    request.session.pop('site_user_name', None)
    messages.success(request, 'Logged out successfully!')
    return redirect(request.META.get('HTTP_REFERER', '/'))


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

def list_users(request):
    users = SiteUser.objects.all().order_by('-id')
    return render(request, 'admin/list_users.html', {'users': users})

def edit_user(request, pk):
    user = get_object_or_404(SiteUser, pk=pk)
    if request.method == 'POST':
        user.name = request.POST.get('name')
        user.place = request.POST.get('place')
        user.email = request.POST.get('email')
        user.phone = request.POST.get('phone')
        user.save()
        messages.success(request, 'User updated successfully.')
        return redirect('list_users')
    return render(request, 'admin/edit_user.html', {'site_user': user})

def delete_user(request, pk):
    user = get_object_or_404(SiteUser, pk=pk)
    if request.method == 'POST':
        user.delete()
        messages.success(request, 'User deleted successfully.')
    return redirect('list_users')

def list_user_data(request):
    orders = Order.objects.all().order_by('-created_at')
    return render(request, 'admin/list_user_data.html', {'orders': orders})

def download_user_data_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="user_orders.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Order ID', 'Date', 'Total Amount', 'Status', 'User Email (Account)', 'Full Name', 'Mobile', 'Contact Email',
        'House/Flat', 'Street/Area', 'Landmark', 'City', 'District',
        'State', 'Country', 'PIN Code', 'Items Ordered', 'Order Notes'
    ])

    orders = Order.objects.all().order_by('-created_at')
    for order in orders:
        items_str = " | ".join([f"{item.quantity}x {item.product_name} (₹{item.price})" for item in order.items.all()])
        writer.writerow([
            order.id,
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            order.total_amount,
            order.status,
            order.user.email if order.user else '',
            order.full_name,
            order.mobile_number,
            order.email_address,
            order.house_flat_number,
            order.street_area,
            order.landmark,
            order.city,
            order.district,
            order.state,
            order.country,
            order.pin_code,
            items_str,
            order.order_notes
        ])

    return response

def checkout(request):
    user_id = request.session.get('site_user_id')
    if not user_id:
        messages.error(request, 'Please login to continue to checkout.')
        return redirect('home')

    user = get_object_or_404(SiteUser, id=user_id)
    user_data = getattr(user, 'user_data', None)

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        mobile_number = request.POST.get('mobile_number')
        email_address = request.POST.get('email_address')
        house_flat_number = request.POST.get('house_flat_number')
        street_area = request.POST.get('street_area')
        landmark = request.POST.get('landmark', '')
        city = request.POST.get('city')
        district = request.POST.get('district')
        state = request.POST.get('state')
        country = request.POST.get('country', 'India')
        pin_code = request.POST.get('pin_code')
        order_notes = request.POST.get('order_notes', '')

        if user_data:
            user_data.full_name = full_name
            user_data.mobile_number = mobile_number
            user_data.email_address = email_address
            user_data.house_flat_number = house_flat_number
            user_data.street_area = street_area
            user_data.landmark = landmark
            user_data.city = city
            user_data.district = district
            user_data.state = state
            user_data.country = country
            user_data.pin_code = pin_code
            user_data.order_notes = order_notes
            user_data.save()
        else:
            UserData.objects.create(
                user=user,
                full_name=full_name,
                mobile_number=mobile_number,
                email_address=email_address,
                house_flat_number=house_flat_number,
                street_area=street_area,
                landmark=landmark,
                city=city,
                district=district,
                state=state,
                country=country,
                pin_code=pin_code,
                order_notes=order_notes
            )
            
        # Parse cart data and create Order
        cart_data_str = request.POST.get('cart_data', '[]')
        try:
            cart_items = json.loads(cart_data_str)
        except json.JSONDecodeError:
            cart_items = []
            
        # Ensure we have items (even if empty, we can create a record, but best if there are items)
        # We will calculate total amount manually from the parsed items
        total_amount = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart_items)
        
        # Create Order Snapshot
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            status='Pending',
            full_name=full_name,
            mobile_number=mobile_number,
            email_address=email_address,
            house_flat_number=house_flat_number,
            street_area=street_area,
            landmark=landmark,
            city=city,
            district=district,
            state=state,
            country=country,
            pin_code=pin_code,
            order_notes=order_notes
        )
        
        # Create Order Items
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product_name=item.get('name', 'Unknown Product'),
                product_type=item.get('type', 'Unknown Type'),
                price=item.get('price', 0),
                quantity=item.get('qty', 1)
            )
        
        return redirect('order_success')

    # For GET request, provide initial data if UserData exists
    context = {}
    if user_data:
        context['user_data'] = user_data
    else:
        # Provide default SiteUser data for email and phone if no UserData exists
        context['user_data'] = {
            'full_name': user.name,
            'mobile_number': user.phone,
            'email_address': user.email
        }

    return render(request, 'product/checkout.html', context)


def order_success(request):
    return render(request, 'product/order_success.html')
