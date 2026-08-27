from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    image = models.ImageField(upload_to='categories/', max_length=255, blank=True, null=True)
    show_in_collection_list = models.BooleanField(default=True)
    show_in_collection_table = models.BooleanField(default=False)

    class Meta:
        db_table = 'category'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Product(models.Model):
    categories = models.ManyToManyField(Category, related_name='products')
    collection_name = models.CharField(max_length=255)
    description = models.TextField()
    fake_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    stock_available = models.BooleanField(default=True)
    show_on_toggle_page = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, blank=True, null=True)

    class Meta:
        db_table = 'product'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return f"{self.collection_name}"

    @property
    def first_image_url(self):
        first_image = self.images.first()
        return first_image.image.url if first_image else ''

    @property
    def stock_status(self):
        if not self.stock_available or self.quantity == 0:
            return 'Stock Not Available'
        return 'In Stock'

    @property
    def has_fake_price(self):
        """True when a struck-through "MRP" should be shown next to price."""
        return self.fake_price is not None and self.fake_price > self.price

    @property
    def discount_percent(self):
        if not self.has_fake_price:
            return 0
        return int(round((float(self.fake_price) - float(self.price)) / float(self.fake_price) * 100))


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/', max_length=255)

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'

    def __str__(self):
        return f"Image for {self.product.collection_name}"


class SiteUser(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True)
    password = models.CharField(max_length=255)

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.name
        
    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class AdminAuth(models.Model):
    """Single-row store for the admin-panel login. Replaces the old
    hardcoded settings.SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD. The password
    is stored hashed. Seeded once by data migration; edited from
    /admin-panel/profile/."""
    username = models.CharField(max_length=255, default='Admin')
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)

    class Meta:
        db_table = 'admin_auth'
        verbose_name = 'Admin Auth'
        verbose_name_plural = 'Admin Auth'

    def __str__(self):
        return self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    @classmethod
    def load(cls):
        return cls.objects.first()


class UserData(models.Model):
    user = models.OneToOneField(SiteUser, on_delete=models.CASCADE, related_name='user_data')
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20)
    email_address = models.EmailField()
    house_flat_number = models.CharField(max_length=255)
    street_area = models.CharField(max_length=255)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    pin_code = models.CharField(max_length=20)
    order_notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'user_data'
        verbose_name = 'User Data'
        verbose_name_plural = 'User Data'

    def __str__(self):
        return f"{self.full_name} ({self.user.email})"


class SavedAddress(models.Model):
    """Up to 3 addresses a user can save at checkout and pick between later,
    instead of retyping shipping details for every order."""
    user = models.ForeignKey(SiteUser, on_delete=models.CASCADE, related_name='saved_addresses')
    label = models.CharField(max_length=50, blank=True)
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20)
    email_address = models.EmailField(blank=True)
    house_flat_number = models.CharField(max_length=255)
    street_area = models.CharField(max_length=255)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    pin_code = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saved_addresses'
        verbose_name = 'Saved Address'
        verbose_name_plural = 'Saved Addresses'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.label or self.full_name} ({self.user.email})"

class Order(models.Model):
    user = models.ForeignKey(SiteUser, on_delete=models.CASCADE, related_name='orders')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=50, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    purchase_type = models.CharField(max_length=50, default='Online')
    payment_type = models.CharField(max_length=50, blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)

    # Set the moment a checkout attempt starts (status='Payment Pending'),
    # not just once it succeeds - needed so the Razorpay webhook (which has
    # no browser session to read) and the stale-pending cleanup routine can
    # both see/reverse what coupon a given attempt claimed.
    coupon_code = models.CharField(max_length=50, blank=True, null=True)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Snapshot of shipping details for this specific order
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20)
    email_address = models.EmailField()
    house_flat_number = models.CharField(max_length=255)
    street_area = models.CharField(max_length=255)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    pin_code = models.CharField(max_length=20)
    order_notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'

    def __str__(self):
        return f"Order #{self.id} by {self.user.email}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_id = models.IntegerField(null=True, blank=True)
    product_image = models.CharField(max_length=500, blank=True, null=True)
    product_name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

class OrderStatus(models.Model):
    status_name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'order_status'
        verbose_name = 'Order Status'
        verbose_name_plural = 'Order Statuses'

    def __str__(self):
        return self.status_name



class ProductCoupon(models.Model):
    DISCOUNT_TYPE_CHOICES = (
        ('flat', 'Flat Amount'),
        ('product_qty', 'Product Qty'),
    )

    coupon_code = models.CharField(max_length=50, unique=True)
    coupon_name = models.CharField(max_length=255)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='flat')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_qty = models.PositiveIntegerField(default=0)
    valid_from = models.DateField()
    valid_until = models.DateField()
    usage_limit = models.PositiveIntegerField(default=0, help_text='0 means unlimited')
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_coupon'
        verbose_name = 'Product Coupon'
        verbose_name_plural = 'Product Coupons'
        ordering = ['-created_at']

    def __str__(self):
        return self.coupon_code

    @property
    def status(self):
        import datetime
        today = datetime.date.today()
        if not self.is_active:
            return 'Inactive'
        if today < self.valid_from:
            return 'Upcoming'
        if today > self.valid_until:
            return 'Expired'
        if self.usage_limit and self.used_count >= self.usage_limit:
            return 'Used Up'
        return 'Active'

    @property
    def discount_display(self):
        return f'₹{self.discount_value}'

    @property
    def condition_display(self):
        if self.discount_type == 'product_qty':
            return f'Min Qty: {self.min_qty} product(s)'
        return f'₹{self.min_order_amount}'


class CartItem(models.Model):
    user = models.ForeignKey(SiteUser, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cart_items'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.quantity} x {self.product.collection_name} ({self.user.email})"


class WishlistItem(models.Model):
    user = models.ForeignKey(SiteUser, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlist_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wishlist_items'
        verbose_name = 'Wishlist Item'
        verbose_name_plural = 'Wishlist Items'
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.product.collection_name} ({self.user.email})"


class UpdationTask(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Updated', 'Updated'),
        ('Completed', 'Completed'),
        ('Invalid', 'Invalid'),
    )
    PRIORITY_CHOICES = (
        ('High', 'High Priority'),
        ('Low', 'Low Priority'),
    )
    issue_related = models.CharField(max_length=255)
    raised_by = models.CharField(max_length=100)
    related_image = models.ImageField(upload_to='updation_images/', max_length=255, blank=True, null=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    purchase_type = models.CharField(max_length=50, default='Online')
    payment_type = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"{self.issue_related} ({self.status})"


class HeroSection(models.Model):
    """Single editable row backing the home-page hero section. Managed from
    the admin panel's "Hero Updation" page - there is only ever one row,
    fetched via HeroSection.load()."""
    hero_content = models.CharField(max_length=255, blank=True, default='')
    hero_para_1 = models.TextField(blank=True, default='')
    hero_para_2 = models.TextField(blank=True, default='')
    hero_image = models.ImageField(upload_to='hero_section/', max_length=255, blank=True, null=True)
    marquee_text = models.CharField(max_length=500, blank=True, default='')
    toggle = models.CharField(max_length=100, blank=True, default='')
    toggle_para = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'hero_section'
        verbose_name = 'Hero Section'
        verbose_name_plural = 'Hero Section'

    def __str__(self):
        return self.hero_content or f'Hero Section #{self.pk}'

    @classmethod
    def load(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class HeroImage(models.Model):
    """One slide of the home-page hero. One row -> static image; several
    rows -> the home page auto-rotates them every 5 seconds."""
    hero = models.ForeignKey(HeroSection, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='hero_section/', max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'hero_image'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'Hero image #{self.pk}'
