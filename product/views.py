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
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .forms import ProductForm, CategoryForm, UpdationTaskForm, ProductCouponForm
from .models import Product, ProductImage, SiteUser, UserData, Order, OrderItem, OrderStatus, Category, UpdationTask, ProductCoupon, CartItem, SavedAddress

import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

PHONE_RE = re.compile(r'^\d{10}$')
PINCODE_RE = re.compile(r'^\d{6}$')

# The five order-progress stages shown on the customer-facing order detail
# stepper and offered in the admin "Update Status" / "Filter by Status"
# dropdowns. 'value' matches the raw (sometimes misspelled, e.g. 'shiped',
# 'deliverd') strings already stored in Order.status so existing data keeps
# working; 'label' is the corrected display text.
ORDER_STATUS_STAGES = [
    {'value': 'order placed', 'label': 'Order Placed'},
    {'value': 'packed', 'label': 'Packed'},
    {'value': 'shiped', 'label': 'Shipped'},
    {'value': 'out of delivery', 'label': 'Out for Delivery'},
    {'value': 'deliverd', 'label': 'Delivered'},
]


def is_valid_phone(value):
    return bool(value) and bool(PHONE_RE.fullmatch(value.strip()))


def is_valid_pincode(value):
    return bool(value) and bool(PINCODE_RE.fullmatch(value.strip()))


def is_valid_email(value):
    if not value:
        return False
    try:
        validate_email(value.strip())
        return True
    except ValidationError:
        return False


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


# How long a checkout attempt can sit at status='Payment Pending' before it's
# treated as abandoned rather than just slow (e.g. a UPI app switch-and-back).
PENDING_ORDER_TIMEOUT_MINUTES = 30


def _cleanup_stale_pending_orders():
    """Deletes checkout attempts that never completed payment (popup closed,
    browser crashed, network dropped) once they're old enough to be clearly
    abandoned. A Payment Pending order never touched stock or the buyer's
    cart, and its only other side effect - provisionally counting toward the
    coupon's usage_count - is reversed here, so deleting it fully rolls the
    attempt back to as if it never happened."""
    cutoff = timezone.now() - datetime.timedelta(minutes=PENDING_ORDER_TIMEOUT_MINUTES)
    stale_orders = list(Order.objects.filter(status='Payment Pending', created_at__lt=cutoff))
    for order in stale_orders:
        if order.coupon_discount and order.coupon_code:
            ProductCoupon.objects.filter(coupon_code__iexact=order.coupon_code).update(
                used_count=Greatest(F('used_count') - 1, Value(0))
            )
        order.delete()


def _finalize_paid_order(order, razorpay_payment_id):
    """Marks a Payment Pending order as paid: flips its status, decrements
    stock for its items, updates the buyer's saved shipping details, and
    clears purchased items from their cart. Idempotent - if `order` is
    already 'Order Placed' (finalized by whichever of the browser callback /
    webhook got here first), this is a no-op and returns False.

    Must be called with `order` already locked via select_for_update()
    inside the caller's `with transaction.atomic():` block, so a webhook
    firing at the same moment as the browser's own verify call can't both
    finalize the same order."""
    if order.status == 'Order Placed':
        return False

    order.status = 'Order Placed'
    order.razorpay_payment_id = razorpay_payment_id
    order.save(update_fields=['status', 'razorpay_payment_id'])

    for item in order.items.all():
        if item.product_id:
            # Locks the product row for the rest of this transaction, same
            # reasoning as the order lock above.
            Product.objects.select_for_update().filter(pk=item.product_id).first()
            Product.objects.filter(pk=item.product_id).update(
                quantity=Greatest(F('quantity') - item.quantity, Value(0))
            )

    shipping = {
        'full_name': order.full_name,
        'mobile_number': order.mobile_number,
        'email_address': order.email_address,
        'house_flat_number': order.house_flat_number,
        'street_area': order.street_area,
        'landmark': order.landmark,
        'city': order.city,
        'district': order.district,
        'state': order.state,
        'country': order.country,
        'pin_code': order.pin_code,
        'order_notes': order.order_notes,
    }
    UserData.objects.update_or_create(user=order.user, defaults=shipping)

    purchased_product_ids = [item.product_id for item in order.items.all() if item.product_id]
    if purchased_product_ids:
        CartItem.objects.filter(user=order.user, product_id__in=purchased_product_ids).delete()

    return True


def _order_email_items(order):
    """Rebuilds the cart_items-shaped list send_order_confirmation_email/
    send_order_acknowledgment_email expect, from an order's own OrderItems -
    works from any context (browser callback or webhook), unlike the old
    session-sourced cart_items."""
    return [
        {
            'name': item.product_name,
            'type': item.product_type,
            'qty': item.quantity,
            'price': float(item.price),
        }
        for item in order.items.all()
    ]


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


def send_order_acknowledgment_email(order, cart_items):
    """Emails the customer (order.email_address) an acknowledgment that
    their order was received. Failures here must never break the checkout
    response, since the order/payment has already succeeded by the time
    this runs."""
    from django.core.mail import send_mail

    product_list = "\n".join(
        f"- {item.get('name', 'Unknown Product')} x {int(item.get('qty', 1))} - "
        f"₹{float(item.get('price', 0)) * int(item.get('qty', 1)):.2f}"
        for item in cart_items
    )
    subtotal = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart_items)

    address_lines = [f"{order.house_flat_number}, {order.street_area}"]
    if order.landmark:
        address_lines.append(order.landmark)
    address_lines.append(f"{order.city}, {order.district}, {order.state} - {order.pin_code}")
    address_lines.append(order.country)
    shipping_address = "\n".join(address_lines)

    subject = f"Order Confirmed ✨ | Natsukashii by Pradhama | Order #{order.id}"

    body = f"""Dear {order.full_name},

Thank you for choosing Natsukashii by Pradhama. \U0001f90d

We're delighted to confirm that we've received your order.

Your Order

Order ID: #{order.id}
Order Date: {order.created_at.strftime('%d %b %Y')}

Items:
{product_list}

Subtotal: ₹{subtotal:.2f}
Shipping: FREE
Total Paid: ₹{order.total_amount}

Delivery Details

{order.full_name}
{shipping_address}
Phone: {order.mobile_number}

Your order is now being carefully prepared and packed. Once it is dispatched, we'll share the courier partner and tracking details with you by email/SMS.

We hope your Natsukashii piece becomes a beautiful part of your celebrations and cherished moments. ✨

Thank you for supporting our small business.

Warmly,
Pradhama
Natsukashii by Pradhama
Traditional Collections
"""

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email_address],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send order acknowledgment email for order #%s', order.id)

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


def product_search(request):
    """Searches products by name/description, matching every word in the
    query (so "red saree" only returns products containing both words,
    in any order/field)."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': True, 'results': []})

    words = query.split()
    filters = Q()
    for word in words:
        filters &= (Q(collection_name__icontains=word) | Q(description__icontains=word))

    products = Product.objects.filter(filters).prefetch_related('images').distinct().order_by('collection_name')[:20]

    results = [{
        'id': p.id,
        'name': p.collection_name,
        'price': float(p.price),
        'image': p.first_image_url,
        'in_stock': p.stock_available and p.quantity > 0,
    } for p in products]

    return JsonResponse({'success': True, 'results': results})


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
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()

            if not (name and email and phone):
                details_error = 'All fields are required.'
            elif not is_valid_email(email):
                details_error = 'Please enter a valid email address.'
            elif not is_valid_phone(phone):
                details_error = 'Phone number must be exactly 10 digits.'
            elif SiteUser.objects.filter(email__iexact=email).exclude(id=site_user.id).exists():
                details_error = 'This email is already used by another account.'
            elif SiteUser.objects.filter(phone=phone).exclude(id=site_user.id).exists():
                details_error = 'This phone number is already used by another account.'
            else:
                site_user.name = name
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
    _cleanup_stale_pending_orders()
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
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match!')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        if not is_valid_email(email):
            messages.error(request, 'Please enter a valid email address.')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        if not is_valid_phone(phone):
            messages.error(request, 'Phone number must be exactly 10 digits.')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        if SiteUser.objects.filter(email=email).exists():
            messages.error(request, 'Email is already registered!')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        if SiteUser.objects.filter(phone=phone).exists():
            messages.error(request, 'Phone number is already registered!')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        user = SiteUser(name=name, email=email, phone=phone)
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

        if not is_valid_phone(phone):
            return JsonResponse({'success': False, 'error': 'Phone number must be exactly 10 digits.'})

        user = SiteUser.objects.filter(phone=phone).first()
        if user:
            # This phone number already belongs to an existing account - never
            # silently overwrite its name/password just because a guest
            # checkout form was submitted with a matching number. Only let
            # them in if the password they typed actually matches.
            if not user.check_password(password):
                return JsonResponse({
                    'success': False,
                    'error': 'This phone number is already registered. Please log in with your password instead.',
                })
        else:
            user = SiteUser(name=name, email=f'guest_{phone}@guest.natsukashii.local', phone=phone)
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
    from django.utils import timezone
    cutoff = timezone.now() - datetime.timedelta(days=15)
    products = Product.objects.filter(created_at__gte=cutoff).prefetch_related('images').order_by('-created_at')
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
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not is_valid_email(email):
            messages.error(request, 'Please enter a valid email address.')
            return render(request, 'admin/edit_user.html', {'site_user': user})

        if not is_valid_phone(phone):
            messages.error(request, 'Phone number must be exactly 10 digits.')
            return render(request, 'admin/edit_user.html', {'site_user': user})

        user.name = request.POST.get('name')
        user.email = email
        user.phone = phone
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

    return render(request, 'admin/list_user_data.html', {
        'orders': orders,
        'statuses': ORDER_STATUS_STAGES,
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


def _validate_coupon(code, total_amount, total_qty):
    """Server-side coupon validation shared by apply_coupon (preview) and
    checkout_create_payment (authoritative, at charge time). Returns
    (discount, error) - error is None on success."""
    coupon = ProductCoupon.objects.filter(coupon_code__iexact=code).first()
    if not coupon:
        return 0, 'Not existing coupon'

    if not coupon.is_active:
        return 0, 'Coupon expired'

    today = datetime.date.today()
    if today < coupon.valid_from or today > coupon.valid_until:
        return 0, 'Coupon expired'

    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        return 0, 'Not existing coupon'

    if coupon.discount_type == 'flat':
        if total_amount < float(coupon.min_order_amount):
            return 0, f"Can't apply the coupon. Purchase minimum ₹{coupon.min_order_amount}"
    elif coupon.discount_type == 'product_qty':
        if total_qty < coupon.min_qty:
            return 0, f'Purchase minimum {coupon.min_qty} product(s)'
    else:
        return 0, 'Invalid coupon type'

    discount = min(float(coupon.discount_value), total_amount)
    return discount, None


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

    discount, error = _validate_coupon(code, total_amount, total_qty)
    if error:
        return JsonResponse({'success': False, 'error': error})

    coupon = ProductCoupon.objects.filter(coupon_code__iexact=code).first()
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
    context['saved_addresses'] = user.saved_addresses.all()

    return render(request, 'product/checkout.html', context)


MAX_SAVED_ADDRESSES = 3


def _saved_address_json(addr):
    return {
        'id': addr.id,
        'label': addr.label,
        'full_name': addr.full_name,
        'mobile_number': addr.mobile_number,
        'email_address': addr.email_address or '',
        'house_flat_number': addr.house_flat_number,
        'street_area': addr.street_area,
        'landmark': addr.landmark or '',
        'city': addr.city,
        'district': addr.district,
        'state': addr.state,
        'country': addr.country,
        'pin_code': addr.pin_code,
    }


def save_address(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    user = get_object_or_404(SiteUser, id=user_id)

    if user.saved_addresses.count() >= MAX_SAVED_ADDRESSES:
        return JsonResponse({
            'success': False,
            'error': f'You can only save up to {MAX_SAVED_ADDRESSES} addresses. Delete one to save a new one.',
        })

    full_name = request.POST.get('full_name', '').strip()
    mobile_number = request.POST.get('mobile_number', '').strip()
    email_address = request.POST.get('email_address', '').strip()
    house_flat_number = request.POST.get('house_flat_number', '').strip()
    street_area = request.POST.get('street_area', '').strip()
    landmark = request.POST.get('landmark', '').strip()
    city = request.POST.get('city', '').strip()
    district = request.POST.get('district', '').strip()
    state = request.POST.get('state', '').strip()
    country = request.POST.get('country', 'India').strip() or 'India'
    pin_code = request.POST.get('pin_code', '').strip()
    label = request.POST.get('label', '').strip()

    if not all([full_name, mobile_number, email_address, house_flat_number, street_area, city, district, state]):
        return JsonResponse({'success': False, 'error': 'Please fill in the shipping address fields before saving.'})

    if not is_valid_phone(mobile_number):
        return JsonResponse({'success': False, 'error': 'Mobile number must be exactly 10 digits.'})

    if not is_valid_email(email_address):
        return JsonResponse({'success': False, 'error': 'Please enter a valid email address.'})

    if not is_valid_pincode(pin_code):
        return JsonResponse({'success': False, 'error': 'PIN code must be exactly 6 digits.'})

    if not label:
        label = f'Address {user.saved_addresses.count() + 1}'

    addr = SavedAddress.objects.create(
        user=user, label=label, full_name=full_name, mobile_number=mobile_number,
        email_address=email_address, house_flat_number=house_flat_number, street_area=street_area,
        landmark=landmark, city=city, district=district, state=state, country=country, pin_code=pin_code,
    )

    addresses = user.saved_addresses.all()
    return JsonResponse({'success': True, 'address': _saved_address_json(addr), 'addresses': [_saved_address_json(a) for a in addresses]})


def delete_address(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    user_id = request.session.get('site_user_id')
    if not user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    SavedAddress.objects.filter(id=pk, user_id=user_id).delete()
    addresses = SavedAddress.objects.filter(user_id=user_id)
    return JsonResponse({'success': True, 'addresses': [_saved_address_json(a) for a in addresses]})


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

    # Re-price every line item from the database - never trust price/qty
    # supplied by the client (cart_data, or the Buy Now flow's ?price= URL
    # param). This is what actually gets charged, so it must come from the
    # DB, not the request.
    verified_items = []
    for entry in cart_items:
        product_id = entry.get('id')
        try:
            qty = int(entry.get('qty', 1))
        except (TypeError, ValueError):
            qty = 1
        if not product_id or qty <= 0:
            continue
        product = Product.objects.filter(pk=product_id).first()
        if not product:
            return JsonResponse({'success': False, 'error': 'One or more items in your cart are no longer available. Please refresh and try again.'})
        if not product.stock_available or product.quantity < qty:
            return JsonResponse({'success': False, 'error': f'"{product.collection_name}" only has {product.quantity} left in stock. Please update your cart.'})
        verified_items.append({
            'id': str(product.id),
            'type': entry.get('type', 'product'),
            'name': product.collection_name,
            'price': float(product.price),
            'image': product.first_image_url,
            'qty': qty,
        })

    if not verified_items:
        return JsonResponse({'success': False, 'error': 'Your cart is empty.'})

    cart_items = verified_items
    total_amount = sum(item['price'] * item['qty'] for item in verified_items)
    total_qty = sum(item['qty'] for item in verified_items)

    coupon_code = request.POST.get('coupon_code', '').strip()
    coupon_discount = 0
    if coupon_code:
        coupon_discount, coupon_error = _validate_coupon(coupon_code, total_amount, total_qty)
        if coupon_error:
            return JsonResponse({'success': False, 'error': coupon_error})

    total_amount -= coupon_discount

    if total_amount <= 0:
        return JsonResponse({'success': False, 'error': 'Invalid order amount.'})

    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return JsonResponse({'success': False, 'error': 'Online payment is not configured yet. Please contact support.'})

    mobile_number = request.POST.get('mobile_number', '').strip()
    # Asked fresh at checkout every time - not pre-filled/reused from the
    # account's registration email or any saved shipping profile.
    email_address = request.POST.get('email_address', '').strip()
    pin_code = request.POST.get('pin_code', '').strip()

    if not is_valid_phone(mobile_number):
        return JsonResponse({'success': False, 'error': 'Mobile number must be exactly 10 digits.'})

    if not is_valid_email(email_address):
        return JsonResponse({'success': False, 'error': 'Please enter a valid email address.'})

    if not is_valid_pincode(pin_code):
        return JsonResponse({'success': False, 'error': 'PIN code must be exactly 6 digits.'})

    shipping = {
        'full_name': request.POST.get('full_name', ''),
        'mobile_number': mobile_number,
        'email_address': email_address,
        'house_flat_number': request.POST.get('house_flat_number', ''),
        'street_area': request.POST.get('street_area', ''),
        'landmark': request.POST.get('landmark', ''),
        'city': request.POST.get('city', ''),
        'district': request.POST.get('district', ''),
        'state': request.POST.get('state', ''),
        'country': request.POST.get('country', 'India'),
        'pin_code': pin_code,
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

    # The Order is created now, at status='Payment Pending', rather than
    # only after the payment succeeds. This is what lets the Razorpay
    # webhook (below) finalize the order with no browser session to read -
    # it just looks the order up by razorpay_order_id. Nothing here touches
    # stock, the cart, or (beyond the provisional coupon count below) any
    # other real side effect, so an abandoned attempt can be fully rolled
    # back later by _cleanup_stale_pending_orders deleting this row.
    _cleanup_stale_pending_orders()

    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            status='Payment Pending',
            purchase_type='Online',
            payment_type='Razorpay',
            razorpay_order_id=razorpay_order['id'],
            coupon_code=coupon_code or None,
            coupon_discount=coupon_discount,
            **shipping
        )

        for item in verified_items:
            OrderItem.objects.create(
                order=order,
                product_id=item['id'],
                product_image=item['image'],
                product_name=item['name'],
                product_type=item['type'],
                price=item['price'],
                quantity=item['qty'],
            )

        if coupon_discount > 0 and coupon_code:
            # Counted the moment a real payment attempt starts (not just on
            # apply/preview), and reversed by _cleanup_stale_pending_orders
            # if this attempt is abandoned - so a coupon's usage_count
            # always reflects orders that actually happened or are still in
            # flight, never a permanently-inflated count from abandoned carts.
            ProductCoupon.objects.filter(coupon_code__iexact=coupon_code).update(
                used_count=F('used_count') + 1
            )

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
    """Verifies the Razorpay payment signature, then finalizes the Payment
    Pending order checkout_create_payment already created for this
    razorpay_order_id. This is the fast path, triggered by Razorpay's JS
    handler the moment the browser sees a successful payment; the
    razorpay_webhook view below is the fallback path that finalizes the same
    order server-side if this call never happens (tab closed, network lost)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    razorpay_signature = request.POST.get('razorpay_signature', '')

    order_lookup = Order.objects.filter(razorpay_order_id=razorpay_order_id).first()
    if not order_lookup:
        return JsonResponse({'success': False, 'error': 'Your checkout session has expired. Please try again.'})

    site_user_id = request.session.get('site_user_id')
    if not site_user_id or order_lookup.user_id != site_user_id:
        return JsonResponse({'success': False, 'error': 'Please login to continue.'})

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'success': False, 'error': 'Payment verification failed.'})

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_lookup.pk)
        newly_finalized = _finalize_paid_order(order, razorpay_payment_id)

    if newly_finalized:
        cart_items = _order_email_items(order)
        send_order_confirmation_email(order, cart_items, order.coupon_code, order.coupon_discount)
        send_order_acknowledgment_email(order, cart_items)

    return JsonResponse({'success': True, 'redirect_url': '/order-success/'})


@csrf_exempt
def razorpay_webhook(request):
    """Razorpay calls this server-to-server the moment a payment is
    captured, independent of whether the customer's browser/tab is even
    still open - this is what actually closes the gap where a captured
    payment could otherwise leave no Order behind (checkout_verify_payment
    alone can't help if the browser never gets to call it).

    Configure this in the Razorpay Dashboard: Settings > Webhooks > add
    webhook, URL = <site>/razorpay/webhook/, subscribe to payment.captured,
    then put the secret it gives you in RAZORPAY_WEBHOOK_SECRET."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not webhook_secret:
        # Not configured in the Razorpay Dashboard yet - nothing to verify
        # the request against, so there's nothing safe to do with it.
        return HttpResponse(status=200)

    signature = request.headers.get('X-Razorpay-Signature', '')
    body = request.body

    client = get_razorpay_client()
    try:
        client.utility.verify_webhook_signature(body.decode('utf-8'), signature, webhook_secret)
    except razorpay.errors.SignatureVerificationError:
        return HttpResponse(status=400)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if payload.get('event') != 'payment.captured':
        # Acknowledge anything we don't act on so Razorpay stops retrying it.
        return HttpResponse(status=200)

    payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    razorpay_order_id = payment_entity.get('order_id')
    razorpay_payment_id = payment_entity.get('id')
    if not razorpay_order_id or not razorpay_payment_id:
        return HttpResponse(status=200)

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(razorpay_order_id=razorpay_order_id).first()
        if not order:
            # Either an order this webhook secret doesn't own, or its
            # Payment Pending row was already cleaned up as stale - either
            # way, nothing to do.
            return HttpResponse(status=200)
        newly_finalized = _finalize_paid_order(order, razorpay_payment_id)

    if newly_finalized:
        cart_items = _order_email_items(order)
        send_order_confirmation_email(order, cart_items, order.coupon_code, order.coupon_discount)
        send_order_acknowledgment_email(order, cart_items)

    return HttpResponse(status=200)


def order_success(request):
    return render(request, 'product/order_success.html')

def my_orders(request):
    _cleanup_stale_pending_orders()
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


def order_detail(request, order_id):
    user_id = request.session.get('site_user_id')
    if not user_id:
        messages.error(request, 'Please login to view your order.')
        return redirect('home')

    user = get_object_or_404(SiteUser, id=user_id)
    order = get_object_or_404(Order.objects.prefetch_related('items'), id=order_id, mobile_number=user.phone)

    status_lower = (order.status or '').strip().lower()
    current_step = 1
    for stage in ORDER_STATUS_STAGES:
        if stage['value'] == status_lower:
            current_step = ORDER_STATUS_STAGES.index(stage) + 1
            break

    return render(request, 'product/order_detail.html', {
        'order': order,
        'stages': ORDER_STATUS_STAGES,
        'current_step': current_step,
        'site_user_name': request.session.get('site_user_name'),
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
    # Each task belongs to exactly one panel - status takes precedence over
    # priority, so once a task moves to Updated/Completed/Invalid it drops
    # out of the priority panels instead of showing up in both places.
    # Priority only matters to sort a still-Pending task into the Pending /
    # High Priority / Low Priority bucket.
    pending_tasks = UpdationTask.objects.filter(
        status='Pending'
    ).filter(Q(priority__isnull=True) | Q(priority='')).order_by('-created_at')
    high_priority_tasks = UpdationTask.objects.filter(status='Pending', priority='High').order_by('-created_at')
    low_priority_tasks = UpdationTask.objects.filter(status='Pending', priority='Low').order_by('-created_at')
    updated_tasks = UpdationTask.objects.filter(status='Updated').order_by('-created_at')
    completed_tasks = UpdationTask.objects.filter(status='Completed').order_by('-created_at')
    invalid_tasks = UpdationTask.objects.filter(status='Invalid').order_by('-created_at')
    return render(request, 'admin/manage_updations.html', {
        'pending_tasks': pending_tasks,
        'updated_tasks': updated_tasks,
        'completed_tasks': completed_tasks,
        'invalid_tasks': invalid_tasks,
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
        if new_status in ['Pending', 'Updated', 'Completed', 'Invalid']:
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

        if not is_valid_phone(mobile_number):
            messages.error(request, 'Mobile number must be exactly 10 digits.')
            return redirect('manual_selling')

        if not is_valid_email(email_address):
            messages.error(request, 'Please enter a valid email address.')
            return redirect('manual_selling')

        if not is_valid_pincode(pin_code):
            messages.error(request, 'PIN code must be exactly 6 digits.')
            return redirect('manual_selling')

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

