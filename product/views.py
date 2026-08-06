from django.http import Http404, JsonResponse, HttpResponse
import csv
import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, F, Q, Value
from django.db.models.functions import Greatest
from django.contrib import messages
from .forms import ProductForm, CategoryForm, UpdationTaskForm, ProductCouponForm
from .models import Product, ProductImage, SiteUser, UserData, Order, OrderItem, OrderStatus, Category, UpdationTask, ProductCoupon

# Create your views here.
def home(request):
    categories = Category.objects.filter(show_in_collection_list=True).prefetch_related('products', 'products__images').order_by('id')
    table_categories = Category.objects.filter(show_in_collection_table=True).prefetch_related('products', 'products__images').order_by('id')
    all_products = Product.objects.all().prefetch_related('images').order_by('-id')
    onam_category = Category.objects.filter(name='Featured Onam Picks').first()
    return render(request, 'product/home.html', {
        'categories': categories,
        'table_categories': table_categories,
        'all_products': all_products,
        'onam_category': onam_category,
    })


def admin_dashboard(request):
    total_product_stock = Product.objects.aggregate(total_stock=Sum('quantity'))['total_stock'] or 0
    total_product_list = Product.objects.count()
    total_orders = Order.objects.count()
    orders_pending = Order.objects.filter(status__icontains='pending').count()
    orders_completed = Order.objects.filter(status__icontains='deliverd').count()

    context = {
        'total_product_stock': total_product_stock,
        'total_product_list': total_product_list,
        'total_orders': total_orders,
        'orders_pending': orders_pending,
        'orders_completed': orders_completed,
    }
    return render(request, 'admin/admin.html', context)


def add_onam_set_mund(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            mund = form.save(commit=False)
            mund.stock_available = request.POST.get('stock_available') == 'on'
            mund.quantity = int(request.POST.get('quantity', 0))
            mund.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=mund, image=image)

            return redirect('list_onam_set_munds')
    else:
        form = ProductForm()

    return render(request, 'product/add_onam_set_mund.html', {'form': form})


# def add_onam_saree(request):
#     if request.method == 'POST':
#         form = ProductForm(request.POST, request.FILES)
#         if form.is_valid():
#             saree = form.save(commit=False)
#             saree.save()

#             images = request.FILES.getlist('images')
#             for image in images:
#                 ProductImage.objects.create(product=saree, image=image)

#             return redirect('admin_dashboard')
#     else:
#         form = ProductForm()

#     return render(request, 'product/add_onam_saree.html', {'form': form})


def add_onam_saree(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)

        if form.is_valid():
            print("FILES:", request.FILES)

            saree = form.save(commit=False)
            saree.save()

            images = request.FILES.getlist("images")
            print("Images count:", len(images))

            for image in images:
                print("Uploading:", image.name)

                obj = ProductImage(product=saree)
                obj.image = image
                obj.save()

                print("Uploaded:", obj.image.url)

            return redirect("admin_dashboard")

    else:
        form = ProductForm()

    return render(request, "product/add_onam_saree.html", {"form": form})


def add_colored_saree(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=saree, image=image)

            return redirect('admin_dashboard')
    else:
        form = ProductForm()

    return render(request, 'product/add_colored_saree.html', {'form': form})


def list_onam_sarees(request):
    sarees = Product.objects.filter(categories__name='Featured Onam Picks').prefetch_related('images')
    return render(request, 'admin/list_onam_sarees.html', {'sarees': sarees})


def list_colored_sarees(request):
    sarees = Product.objects.filter(categories__name='Most Purchased Sarees').prefetch_related('images')
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

def guest_login(request):
    if request.method == 'POST':
        name = request.POST.get('guest_name', '').strip()
        phone = request.POST.get('guest_phone', '').strip()
        password = request.POST.get('guest_password', '').strip()

        if not name or not phone or not password:
            return JsonResponse({'success': False, 'error': 'Name, phone number and password are required.'})

        user = SiteUser.objects.filter(phone=phone).first()
        if user:
            user.name = name
            user.set_password(password)
            user.save(update_fields=['name', 'password'])
        else:
            user = SiteUser(name=name, place='', email=f'guest_{phone}@guest.natsukashii.local', phone=phone)
            user.set_password(password)
            user.save()

        request.session['site_user_id'] = user.id
        request.session['site_user_name'] = 'Guest'
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def logout_user(request):
    request.session.pop('site_user_id', None)
    request.session.pop('site_user_name', None)
    messages.success(request, 'Logged out successfully!')
    return redirect(request.META.get('HTTP_REFERER', '/'))


def list_onam_set_munds(request):
    munds = Product.objects.filter(categories__name='Shop By Collection').prefetch_related('images')
    return render(request, 'admin/list_onam_set_munds.html', {'munds': munds})


def edit_onam_saree(request, pk):
    saree = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=saree)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.stock_available = request.POST.get('stock_available') == 'on'
            saree.quantity = int(request.POST.get('quantity', 0))
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=saree, image=image)

            return redirect('list_onam_sarees')
    else:
        form = ProductForm(instance=saree)

    return render(request, 'admin/edit_onam_saree.html', {'form': form, 'saree': saree})


def edit_colored_saree(request, pk):
    saree = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=saree)
        if form.is_valid():
            saree = form.save(commit=False)
            saree.stock_available = request.POST.get('stock_available') == 'on'
            saree.quantity = int(request.POST.get('quantity', 0))
            saree.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=saree, image=image)

            return redirect('list_colored_sarees')
    else:
        form = ProductForm(instance=saree)

    return render(request, 'admin/edit_colored_saree.html', {'form': form, 'saree': saree})


def delete_onam_saree(request, pk):
    saree = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        saree.delete()
    return redirect('list_onam_sarees')


def delete_colored_saree(request, pk):
    saree = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        saree.delete()
    return redirect('list_colored_sarees')


def edit_onam_set_mund(request, pk):
    mund = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=mund)
        if form.is_valid():
            mund = form.save(commit=False)
            mund.stock_available = request.POST.get('stock_available') == 'on'
            mund.quantity = int(request.POST.get('quantity', 0))
            mund.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=mund, image=image)

            return redirect('list_onam_set_munds')
    else:
        form = ProductForm(instance=mund)

    return render(request, 'admin/edit_onam_set_mund.html', {'form': form, 'mund': mund})


def delete_onam_set_mund(request, pk):
    mund = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        mund.delete()
    return redirect('list_onam_set_munds')


def onam_saree_explore(request):
    sarees = Product.objects.filter(categories__name='Featured Onam Picks').prefetch_related('images')
    return render(request, 'product/onam_saree_explore.html', {'sarees': sarees})


def colored_saree_explore(request):
    sarees = Product.objects.filter(categories__name='Most Purchased Sarees').prefetch_related('images')
    return render(request, 'product/colored_saree_explore.html', {'sarees': sarees})


def onam_mund_explore(request):
    munds = Product.objects.filter(categories__name='Shop By Collection').prefetch_related('images')
    return render(request, 'product/onam_mund_explore.html', {'munds': munds})


PRODUCT_MODEL_BY_TYPE = {'saree': Product, 'mund': Product, 'colored': Product, 'product': Product}


def category_products(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = category.products.all().prefetch_related('images')
    return render(request, 'product/category_products.html', {'category': category, 'products': products})

def new_arrivals(request):
    products = Product.objects.all().prefetch_related('images').order_by('-id')
    return render(request, 'product/new_arrivals.html', {'products': products})

def all_collections(request):
    categories = Category.objects.filter(show_in_collection_list=True).order_by('name')
    products = Product.objects.filter(categories__show_in_collection_list=True).distinct().prefetch_related('images', 'categories').order_by('-id')
    return render(request, 'product/all_collections.html', {'categories': categories, 'products': products})


def nav_categories_context(request):
    try:
        categories = Category.objects.filter(show_in_collection_table=True).order_by('name')
    except Exception:
        categories = []
    return {'nav_categories': categories}


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

from django.db.models.functions import Lower

def list_user_data(request):
    allowed_statuses = [
        'pending', 'confirmed', 'processing', 'packed', 'shiped', 
        'out of delivery', 'deliverd', 'order placed'
    ]
    
    # Exclude delivered orders from this view, but keep others in allowed_statuses
    orders_query = Order.objects.annotate(status_lower=Lower('status')).filter(status_lower__in=allowed_statuses).exclude(status_lower='deliverd')

    status_filter = request.GET.get('status_filter')
    if status_filter:
        orders = orders_query.filter(status_lower=status_filter.lower()).order_by('-created_at')
    else:
        orders = orders_query.order_by('-created_at')
    
    statuses = OrderStatus.objects.filter(status_name__in=allowed_statuses)
    return render(request, 'admin/list_user_data.html', {
        'orders': orders, 
        'statuses': statuses,
        'current_filter': status_filter
    })

def list_delivered_orders(request):
    allowed_statuses = [
        'deliverd', 'cancelled', 'return requested', 'return rejected', 
        'return approved', 'returened', 'refund initiated', 'refund completed'
    ]
    
    orders_query = Order.objects.annotate(status_lower=Lower('status')).filter(status_lower__in=allowed_statuses)
    
    status_filter = request.GET.get('status_filter')
    if status_filter:
        orders = orders_query.filter(status_lower=status_filter.lower()).order_by('-created_at')
    else:
        orders = orders_query.order_by('-created_at')
        
    statuses = OrderStatus.objects.filter(status_name__in=allowed_statuses)
    return render(request, 'admin/list_delivered_orders.html', {
        'orders': orders, 
        'statuses': statuses,
        'current_filter': status_filter
    })

def update_order_status(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        if new_status:
            order.status = new_status
            order.save()
            messages.success(request, f'Order #{order.id} status updated to {new_status}.')
        else:
            messages.error(request, 'Failed to update order status.')
    return redirect('list_user_data')

def delete_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        order.delete()
        messages.success(request, f'Order #{order.id} has been deleted.')
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('list_user_data')

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

def lookup_coupon(request):
    code = request.GET.get('code', '').strip()
    if not code:
        return JsonResponse({'found': False})
    coupon = ProductCoupon.objects.filter(coupon_code__iexact=code).first()
    if coupon:
        return JsonResponse({'found': True, 'coupon_name': coupon.coupon_name})
    return JsonResponse({'found': False})


def apply_coupon(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    code = request.POST.get('coupon_code', '').strip()
    cart_data_str = request.POST.get('cart_data', '[]')
    try:
        cart_items = json.loads(cart_data_str)
    except json.JSONDecodeError:
        cart_items = []

    total_amount = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart_items)
    total_qty = sum(int(item.get('qty', 1)) for item in cart_items)

    coupon = ProductCoupon.objects.filter(coupon_code__iexact=code).first()
    if not coupon:
        return JsonResponse({'success': False, 'error': 'Not existing coupon'})

    if not coupon.is_active:
        return JsonResponse({'success': False, 'error': 'Coupon expired'})

    today = datetime.date.today()
    if today < coupon.valid_from or today > coupon.valid_until:
        return JsonResponse({'success': False, 'error': 'Coupon expired'})

    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        return JsonResponse({'success': False, 'error': 'Not existing coupon'})

    if coupon.discount_type == 'flat':
        if total_amount < float(coupon.min_order_amount):
            return JsonResponse({'success': False, 'error': f"Can't apply the coupon. Purchase minimum ₹{coupon.min_order_amount}"})
    elif coupon.discount_type == 'product_qty':
        if total_qty < coupon.min_qty:
            return JsonResponse({'success': False, 'error': f'Purchase minimum {coupon.min_qty} product(s)'})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid coupon type'})

    discount = min(float(coupon.discount_value), total_amount)
    new_total = total_amount - discount

    # Usage is only counted once the order is actually placed (see `checkout` view),
    # not just when the coupon is applied/previewed here.

    return JsonResponse({
        'success': True,
        'coupon_name': coupon.coupon_name,
        'discount': discount,
        'total_amount': total_amount,
        'new_total': new_total,
    })


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

        try:
            coupon_discount = float(request.POST.get('coupon_discount', 0) or 0)
        except ValueError:
            coupon_discount = 0
        coupon_discount = max(0, min(coupon_discount, total_amount))
        total_amount -= coupon_discount
        applied_coupon_code = request.POST.get('coupon_code', '').strip()

        # Create Order Snapshot, Order Items, and reduce stock atomically
        with transaction.atomic():
            if coupon_discount > 0 and applied_coupon_code:
                ProductCoupon.objects.filter(coupon_code__iexact=applied_coupon_code).update(
                    used_count=F('used_count') + 1
                )

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

            for item in cart_items:
                product_id = item.get('id')
                qty = int(item.get('qty', 1))

                OrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    product_image=item.get('image'),
                    product_name=item.get('name', 'Unknown Product'),
                    product_type=item.get('type', 'Unknown Type'),
                    price=item.get('price', 0),
                    quantity=qty
                )

                if product_id:
                    Product.objects.filter(pk=product_id).update(
                        quantity=Greatest(F('quantity') - qty, Value(0))
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

def my_orders(request):
    user_id = request.session.get('site_user_id')
    
    previous_statuses = [
        'deliverd', 'cancelled', 'return requested', 'return rejected', 
        'return approved', 'returened', 'refund initiated', 'refund completed'
    ]
    
    if user_id:
        user = get_object_or_404(SiteUser, id=user_id)
        all_orders = Order.objects.annotate(status_lower=Lower('status')).filter(mobile_number=user.phone).prefetch_related('items').order_by('-created_at')
        active_orders = all_orders.exclude(status_lower__in=previous_statuses)
        previous_orders = all_orders.filter(status_lower__in=previous_statuses)
    else:
        active_orders = []
        previous_orders = []

    return render(request, 'product/my_orders.html', {
        'active_orders': active_orders,
        'previous_orders': previous_orders,
        'site_user_name': request.session.get('site_user_name')
    })

# Category CRUD
def list_categories(request):
    categories = Category.objects.all()
    return render(request, 'admin/list_categories.html', {'categories': categories})

def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category added successfully.')
            return redirect('list_categories')
    else:
        form = CategoryForm()
    return render(request, 'admin/add_category.html', {'form': form})

def edit_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully.')
            return redirect('list_categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'admin/edit_category.html', {'form': form, 'category': category})

def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category deleted successfully.')
        return redirect('list_categories')
    return redirect('list_categories')

def category_permissions(request):
    categories = Category.objects.all().order_by('name')
    return render(request, 'admin/category_permissions.html', {'categories': categories})

def update_category_permission(request):
    if request.method == 'POST':
        category = get_object_or_404(Category, pk=request.POST.get('category_id'))
        field = request.POST.get('field')
        value = request.POST.get('value') == 'true'

        if field == 'table':
            category.show_in_collection_table = value
            if value:
                category.show_in_collection_list = True
        elif field == 'list':
            category.show_in_collection_list = value
            if not value:
                category.show_in_collection_table = False
        else:
            return JsonResponse({'success': False, 'error': 'Invalid field'})

        category.save(update_fields=['show_in_collection_list', 'show_in_collection_table'])
        return JsonResponse({
            'success': True,
            'show_in_collection_list': category.show_in_collection_list,
            'show_in_collection_table': category.show_in_collection_table,
        })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Product Coupon CRUD
def list_coupons(request):
    if request.method == 'POST':
        form = ProductCouponForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon created successfully.')
            return redirect('list_coupons')
    else:
        form = ProductCouponForm()

    coupons = ProductCoupon.objects.all()
    return render(request, 'admin/list_coupons.html', {'form': form, 'coupons': coupons})

def edit_coupon(request, pk):
    coupon = get_object_or_404(ProductCoupon, pk=pk)
    if request.method == 'POST':
        form = ProductCouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon updated successfully.')
            return redirect('list_coupons')
    else:
        form = ProductCouponForm(instance=coupon)
    return render(request, 'admin/edit_coupon.html', {'form': form, 'coupon': coupon})

def delete_coupon(request, pk):
    coupon = get_object_or_404(ProductCoupon, pk=pk)
    if request.method == 'POST':
        coupon.delete()
        messages.success(request, 'Coupon deleted successfully.')
        return redirect('list_coupons')
    return redirect('list_coupons')

# Product CRUD
def list_products(request):
    products = Product.objects.prefetch_related('categories', 'images').all().order_by('-id')
    all_categories = Category.objects.all()
    return render(request, 'admin/list_products.html', {'products': products, 'all_categories': all_categories})

def update_product_categories(request, pk):
    if request.method == 'POST':
        product = get_object_or_404(Product, pk=pk)
        category_ids = request.POST.getlist('categories')
        product.categories.set(category_ids)
        messages.success(request, f'Categories updated for {product.collection_name}.')
    return redirect('list_products')

def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.stock_available = request.POST.get('stock_available') == 'on'
            product.quantity = int(request.POST.get('quantity', 0))
            product.save()

            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(product=product, image=image)

            messages.success(request, 'Product added successfully.')
            return redirect('list_products')
    else:
        form = ProductForm()
    return render(request, 'admin/add_product.html', {'form': form})

def edit_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            prod = form.save(commit=False)
            prod.stock_available = request.POST.get('stock_available') == 'on'
            prod.quantity = int(request.POST.get('quantity', 0))
            prod.save()

            images = request.FILES.getlist('images')
            if images:  # Only add new images if they uploaded any
                for image in images:
                    ProductImage.objects.create(product=prod, image=image)

            messages.success(request, 'Product updated successfully.')
            return redirect('list_products')
    else:
        form = ProductForm(instance=product)
    return render(request, 'admin/edit_product.html', {'form': form, 'product': product})

def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted successfully.')
        return redirect('list_products')
    return redirect('list_products')

def delete_product_image(request, pk):
    image = get_object_or_404(ProductImage, pk=pk)
    if request.method == 'POST':
        product_id = image.product.id
        image.delete()
        messages.success(request, 'Image deleted successfully.')
        return redirect('edit_product', pk=product_id)
    return redirect('list_products')

# Updations Tracker
def manage_updations(request):
    pending_tasks = UpdationTask.objects.filter(status='Pending').order_by('-created_at')
    completed_tasks = UpdationTask.objects.filter(status='Completed').order_by('-created_at')
    return render(request, 'admin/manage_updations.html', {
        'pending_tasks': pending_tasks,
        'completed_tasks': completed_tasks
    })

def add_updation(request):
    if request.method == 'POST':
        form = UpdationTaskForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Updation logged successfully.')
            return redirect('manage_updations')
    else:
        form = UpdationTaskForm()
    return render(request, 'admin/add_updation.html', {'form': form})

def update_updation_status(request, pk):
    task = get_object_or_404(UpdationTask, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['Pending', 'Completed']:
            task.status = new_status
            task.save()
            messages.success(request, f'Updation status updated to {new_status}.')
    return redirect('manage_updations')


def updations_context(request):
    from .models import UpdationTask
    try:
        count = UpdationTask.objects.filter(status='Pending').count()
    except Exception:
        count = 0
    return {'pending_count': count}

def manual_selling(request):
    from .models import Product, SiteUser, Order, OrderItem
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
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
        
        payment_type = request.POST.get('payment_type')
        
        site_user = get_object_or_404(SiteUser, id=user_id)
        product = get_object_or_404(Product, id=product_id)
        
        total_amount = product.price * quantity

        with transaction.atomic():
            order = Order.objects.create(
                user=site_user,
                total_amount=total_amount,
                status='Order Placed',
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
                order_notes=order_notes,
                purchase_type='Manual',
                payment_type=payment_type
            )

            OrderItem.objects.create(
                order=order,
                product_id=product.id,
                product_image=product.first_image_url,
                product_name=product.collection_name,
                product_type='',
                price=product.price,
                quantity=quantity
            )

            Product.objects.filter(pk=product.id).update(
                quantity=Greatest(F('quantity') - quantity, Value(0))
            )

        messages.success(request, f'Manual order created successfully for {full_name}!')
        return redirect('list_user_data')
        
    products = Product.objects.all()
    from .models import SiteUser
    users = SiteUser.objects.all()
    
    return render(request, 'admin/manual_selling.html', {
        'products': products,
        'users': users
    })


def our_story(request):
    return render(request, 'product/our_story.html')

def refund_policy(request):
    return render(request, 'product/refund_policy.html')

