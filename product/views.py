from django.http import Http404, JsonResponse, HttpResponse
import csv
import json
import datetime
import razorpay
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, F, Q, Value
from django.db.models.functions import Greatest
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from .forms import ProductForm, CategoryForm, UpdationTaskForm, ProductCouponForm
from .models import Product, ProductImage, SiteUser, UserData, Order, OrderItem, OrderStatus, Category, UpdationTask, ProductCoupon, CartItem, WishlistItem


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def send_order_confirmation_email(order, cart_items, coupon_code, coupon_discount):
    """Emails a full order summary to the store's own inbox after a payment
    is confirmed. Failures here must never break the checkout response, since
    the order/payment has already succeeded by the time this runs."""
    from django.core.mail import send_mail

    lines = [
        f"New order placed - Order #{order.id}",
        "",
        f"Order date: {order.created_at.strftime('%d %b %Y, %I:%M %p')}",
        f"Purchase type: {order.purchase_type}",
        f"Payment type: {order.payment_type}",
        f"Order status: {order.status}",
        f"Razorpay order ID: {order.razorpay_order_id}",
        f"Razorpay payment ID: {order.razorpay_payment_id}",
        "",
        "Customer details",
        "-----------------",
        f"Name: {order.full_name}",
        f"Email: {order.email_address}",
        f"Mobile: {order.mobile_number}",
        "",
        "Shipping address",
        "-----------------",
        f"{order.house_flat_number}, {order.street_area}",
        f"{order.landmark}" if order.landmark else "",
        f"{order.city}, {order.district}, {order.state} - {order.pin_code}",
        f"{order.country}",
        f"Order notes: {order.order_notes}" if order.order_notes else "",
        "",
        "Products",
        "-----------------",
    ]

    subtotal = 0
    for item in cart_items:
        name = item.get('name', 'Unknown Product')
        item_type = item.get('type', '')
        qty = int(item.get('qty', 1))
        price = float(item.get('price', 0))
        line_total = price * qty
        subtotal += line_total
        lines.append(f"- {name} ({item_type}) x {qty} @ Rs.{price:.2f} = Rs.{line_total:.2f}")

    lines += [
        "",
        f"Subtotal: Rs.{subtotal:.2f}",
    ]
    if coupon_discount:
        lines.append(f"Coupon applied: {coupon_code} (-Rs.{float(coupon_discount):.2f})")
    lines.append(f"Total paid: Rs.{order.total_amount}")

    body = "\n".join(line for line in lines if line is not None)

    try:
        send_mail(
            subject=f"New Order #{order.id} - {order.full_name}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ORDER_NOTIFICATION_EMAIL],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send order confirmation email for order #%s', order.id)

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


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')

    error = None
    next_url = request.POST.get('next') or request.GET.get('next') or ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            # Point 8: admin session must not survive a browser close.
            request.session.set_expiry(0)
            return redirect(next_url or 'admin_dashboard')
        error = 'Invalid username or password.'

    return render(request, 'admin/admin_login.html', {'error': error, 'next': next_url})


def admin_logout(request):
    logout(request)
    return redirect('home')


def admin_logout_all_devices(request):
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    user_id = request.user.id
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user_id):
            session.delete()

    logout(request)
    messages.success(request, 'Logged out from all devices. Please log in again.')
    return redirect('admin_login')


def admin_profile(request):
    site_user = None
    site_user_id = request.session.get('site_user_id')
    if site_user_id:
        site_user = SiteUser.objects.filter(id=site_user_id).first()

    details_error = None
    details_success = False
    site_password_error = None
    site_password_success = False
    password_error = None
    password_success = False

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'site_details' and site_user:
            name = request.POST.get('name', '').strip()
            place = request.POST.get('place', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()

            if not (name and place and email and phone):
                details_error = 'All fields are required.'
            elif SiteUser.objects.filter(email__iexact=email).exclude(id=site_user.id).exists():
                details_error = 'This email is already used by another account.'
            elif SiteUser.objects.filter(phone=phone).exclude(id=site_user.id).exists():
                details_error = 'This phone number is already used by another account.'
            else:
                site_user.name = name
                site_user.place = place
                site_user.email = email
                site_user.phone = phone
                site_user.save()
                request.session['site_user_name'] = site_user.name
                details_success = True

        elif form_type == 'site_password' and site_user:
            old_password = request.POST.get('site_old_password', '')
            new_password = request.POST.get('site_new_password', '')
            confirm_password = request.POST.get('site_confirm_password', '')

            if not site_user.check_password(old_password):
                site_password_error = 'Current password is incorrect.'
            elif len(new_password) < 8:
                site_password_error = 'New password must be at least 8 characters.'
            elif new_password != confirm_password:
                site_password_error = 'New password and confirm password do not match.'
            else:
                site_user.set_password(new_password)
                site_user.save()
                site_password_success = True

        elif form_type == 'admin_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not request.user.check_password(old_password):
                password_error = 'Current password is incorrect.'
            elif len(new_password) < 8:
                password_error = 'New password must be at least 8 characters.'
            elif new_password != confirm_password:
                password_error = 'New password and confirm password do not match.'
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                password_success = True

    return render(request, 'admin/admin_profile.html', {
        'site_user': site_user,
        'details_error': details_error,
        'details_success': details_success,
        'site_password_error': site_password_error,
        'site_password_success': site_password_success,
        'password_error': password_error,
        'password_success': password_success,
    })


def admin_dashboard(request):
    total_product_stock = Product.objects.aggregate(total_stock=Sum('quantity'))['total_stock'] or 0
    total_product_list = Product.objects.count()
    total_orders = Order.objects.count()
    orders_pending = Order.objects.filter(status__icontains='pending').count()
    orders_completed = Order.objects.filter(status__icontains='deliverd').count()

    recent_completed_orders = Order.objects.filter(status__icontains='deliverd').prefetch_related('items').order_by('-created_at')[:10]

    context = {
        'total_product_stock': total_product_stock,
        'total_product_list': total_product_list,
        'total_orders': total_orders,
        'orders_pending': orders_pending,
        'orders_completed': orders_completed,
        'recent_completed_orders': recent_completed_orders,
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

        if SiteUser.objects.filter(phone=phone).exists():
            messages.error(request, 'Phone number is already registered!')
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
        login_id = request.POST.get('email', '').strip() # It comes from the name="email" input, but can be phone, email, or (for guest accounts) name
        password = request.POST.get('password')

        user = SiteUser.objects.filter(Q(email__iexact=login_id) | Q(phone=login_id)).first()
        if not user:
            # Guest checkout doesn't ask for a separate username, so also allow
            # logging back in with the name that was entered during guest checkout.
            name_matches = SiteUser.objects.filter(name__iexact=login_id)
            if name_matches.count() == 1:
                user = name_matches.first()

        if not user:
            return JsonResponse({'success': False, 'error': 'failed to login invalid email or phone number'})

        if user.check_password(password):
            request.session['site_user_id'] = user.id
            request.session['site_user_name'] = user.name
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'failed to login invalid password'})
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
        request.session['site_user_name'] = user.name
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
    context['razorpay_key_id'] = settings.RAZORPAY_KEY_ID

    return render(request, 'product/checkout.html', context)


def _cart_item_json(item):
    product = item.product
    return {
        'id': str(product.id),
        'type': 'product',
        'name': product.collection_name,
        'price': float(product.price),
        'image': product.first_image_url,
        'qty': item.quantity,
    }


def _wishlist_item_json(item):
    product = item.product
    return {
        'id': str(product.id),
        'type': 'product',
        'name': product.collection_name,
        'price': float(product.price),
        'image': product.first_image_url,
    }


def cart_list(request):
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': True, 'items': []})
    items = CartItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_cart_item_json(i) for i in items]})


def cart_add(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    product_id = request.POST.get('product_id')
    product = get_object_or_404(Product, pk=product_id)
    CartItem.objects.get_or_create(user_id=user_id, product=product, defaults={'quantity': 1})

    items = CartItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_cart_item_json(i) for i in items]})


def cart_update(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    product_id = request.POST.get('product_id')
    try:
        qty = int(request.POST.get('qty', 1))
    except ValueError:
        qty = 1

    if qty <= 0:
        CartItem.objects.filter(user_id=user_id, product_id=product_id).delete()
    else:
        CartItem.objects.filter(user_id=user_id, product_id=product_id).update(quantity=qty)

    items = CartItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_cart_item_json(i) for i in items]})


def cart_remove(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    product_id = request.POST.get('product_id')
    CartItem.objects.filter(user_id=user_id, product_id=product_id).delete()

    items = CartItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_cart_item_json(i) for i in items]})


def cart_merge(request):
    """Merges a browser's locally-cached cart (from before server-side sync,
    or an offline queue) into the account's server-side cart, without
    dropping items already saved server-side from another browser."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    try:
        incoming = json.loads(request.POST.get('items', '[]'))
    except json.JSONDecodeError:
        incoming = []

    for entry in incoming:
        product_id = entry.get('id')
        try:
            qty = int(entry.get('qty', 1))
        except (TypeError, ValueError):
            qty = 1
        if not product_id or qty <= 0:
            continue
        if not Product.objects.filter(pk=product_id).exists():
            continue

        cart_item, created = CartItem.objects.get_or_create(
            user_id=user_id, product_id=product_id, defaults={'quantity': qty}
        )
        if not created and qty > cart_item.quantity:
            cart_item.quantity = qty
            cart_item.save(update_fields=['quantity'])

    items = CartItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_cart_item_json(i) for i in items]})


def wishlist_list(request):
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': True, 'items': []})
    items = WishlistItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_wishlist_item_json(i) for i in items]})


def wishlist_toggle(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    product_id = request.POST.get('product_id')
    product = get_object_or_404(Product, pk=product_id)

    existing = WishlistItem.objects.filter(user_id=user_id, product=product).first()
    if existing:
        existing.delete()
    else:
        WishlistItem.objects.create(user_id=user_id, product=product)

    items = WishlistItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_wishlist_item_json(i) for i in items]})


def wishlist_remove(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    product_id = request.POST.get('product_id')
    WishlistItem.objects.filter(user_id=user_id, product_id=product_id).delete()

    items = WishlistItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_wishlist_item_json(i) for i in items]})


def wishlist_merge(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    try:
        incoming = json.loads(request.POST.get('items', '[]'))
    except json.JSONDecodeError:
        incoming = []

    for entry in incoming:
        product_id = entry.get('id')
        if not product_id or not Product.objects.filter(pk=product_id).exists():
            continue
        WishlistItem.objects.get_or_create(user_id=user_id, product_id=product_id)

    items = WishlistItem.objects.filter(user_id=user_id).select_related('product').order_by('added_at')
    return JsonResponse({'success': True, 'items': [_wishlist_item_json(i) for i in items]})


def checkout_create_payment(request):
    """Creates a Razorpay order for the current cart and stashes the pending
    order details in the session. No Order/OrderItem rows are created here -
    those only get created once the payment is verified as successful."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue to checkout.'})

    user = get_object_or_404(SiteUser, id=user_id)

    cart_data_str = request.POST.get('cart_data', '[]')
    try:
        cart_items = json.loads(cart_data_str)
    except json.JSONDecodeError:
        cart_items = []

    if not cart_items:
        return JsonResponse({'success': False, 'error': 'Your cart is empty.'})

    total_amount = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart_items)

    try:
        coupon_discount = float(request.POST.get('coupon_discount', 0) or 0)
    except ValueError:
        coupon_discount = 0
    coupon_discount = max(0, min(coupon_discount, total_amount))
    total_amount -= coupon_discount

    if total_amount <= 0:
        return JsonResponse({'success': False, 'error': 'Invalid order amount.'})

    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return JsonResponse({'success': False, 'error': 'Online payment is not configured yet. Please contact support.'})

    shipping = {
        'full_name': request.POST.get('full_name', ''),
        'mobile_number': request.POST.get('mobile_number', ''),
        'email_address': request.POST.get('email_address', ''),
        'house_flat_number': request.POST.get('house_flat_number', ''),
        'street_area': request.POST.get('street_area', ''),
        'landmark': request.POST.get('landmark', ''),
        'city': request.POST.get('city', ''),
        'district': request.POST.get('district', ''),
        'state': request.POST.get('state', ''),
        'country': request.POST.get('country', 'India'),
        'pin_code': request.POST.get('pin_code', ''),
        'order_notes': request.POST.get('order_notes', ''),
    }

    amount_paise = int(round(total_amount * 100))

    try:
        client = get_razorpay_client()
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
        })
    except Exception:
        logger.exception('Razorpay order creation failed')
        return JsonResponse({'success': False, 'error': 'Unable to start payment. Please try again.'})

    request.session['pending_order'] = {
        'razorpay_order_id': razorpay_order['id'],
        'user_id': user.id,
        'cart_items': cart_items,
        'coupon_code': request.POST.get('coupon_code', '').strip(),
        'coupon_discount': coupon_discount,
        'total_amount': total_amount,
        'shipping': shipping,
    }

    return JsonResponse({
        'success': True,
        'key_id': settings.RAZORPAY_KEY_ID,
        'razorpay_order_id': razorpay_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'name': 'Natsukashii',
        'description': 'Order Payment',
        'prefill_name': shipping['full_name'],
        'prefill_email': shipping['email_address'],
        'prefill_contact': shipping['mobile_number'],
    })


def checkout_verify_payment(request):
    """Verifies the Razorpay payment signature and only then creates the
    Order, OrderItems, reduces stock and counts coupon usage."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    pending = request.session.get('pending_order')
    if not pending:
        return JsonResponse({'success': False, 'error': 'Your checkout session has expired. Please try again.'})

    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    razorpay_signature = request.POST.get('razorpay_signature', '')

    if razorpay_order_id != pending.get('razorpay_order_id'):
        return JsonResponse({'success': False, 'error': 'Order mismatch. Please try again.'})

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'success': False, 'error': 'Payment verification failed.'})

    user = get_object_or_404(SiteUser, id=pending['user_id'])
    shipping = pending['shipping']
    cart_items = pending['cart_items']
    coupon_code = pending.get('coupon_code')
    coupon_discount = pending.get('coupon_discount', 0)
    total_amount = pending.get('total_amount', 0)

    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            status='Order Placed',
            purchase_type='Online',
            payment_type='Razorpay',
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            **shipping
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

        if coupon_discount > 0 and coupon_code:
            ProductCoupon.objects.filter(coupon_code__iexact=coupon_code).update(
                used_count=F('used_count') + 1
            )

        UserData.objects.update_or_create(user=user, defaults=shipping)

        purchased_product_ids = [item.get('id') for item in cart_items if item.get('id')]
        if purchased_product_ids:
            CartItem.objects.filter(user=user, product_id__in=purchased_product_ids).delete()

    del request.session['pending_order']

    send_order_confirmation_email(order, cart_items, coupon_code, coupon_discount)

    return JsonResponse({'success': True, 'redirect_url': '/order-success/'})


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
    updated_tasks = UpdationTask.objects.filter(status='Updated').order_by('-created_at')
    completed_tasks = UpdationTask.objects.filter(status='Completed').order_by('-created_at')
    high_priority_tasks = UpdationTask.objects.filter(priority='High').order_by('-created_at')
    low_priority_tasks = UpdationTask.objects.filter(priority='Low').order_by('-created_at')
    return render(request, 'admin/manage_updations.html', {
        'pending_tasks': pending_tasks,
        'updated_tasks': updated_tasks,
        'completed_tasks': completed_tasks,
        'high_priority_tasks': high_priority_tasks,
        'low_priority_tasks': low_priority_tasks,
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
        if new_status in ['Pending', 'Updated', 'Completed']:
            task.status = new_status
            task.save()
            messages.success(request, f'Updation status updated to {new_status}.')
    return redirect('manage_updations')

def update_updation_priority(request, pk):
    task = get_object_or_404(UpdationTask, pk=pk)
    if request.method == 'POST':
        new_priority = request.POST.get('priority')
        if new_priority in ['High', 'Low']:
            task.priority = new_priority
            task.save()
            messages.success(request, f'Updation marked as {new_priority} Priority.')
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

def report_issue(request):
    if request.method == 'POST':
        form = UpdationTaskForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

