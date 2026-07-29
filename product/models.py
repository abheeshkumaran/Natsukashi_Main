from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.hashers import make_password, check_password


class OnamSaree(models.Model):
    collection_name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    stock_available = models.BooleanField(default=True)

    class Meta:
        db_table = 'featured_onam_picks'
        verbose_name = 'FEATURED ONAM PICKS PICKS'
        verbose_name_plural = 'FEATURED ONAM PICKS PICKS'

    def __str__(self):
        return self.collection_name

    @property
    def first_image_url(self):
        first_image = self.images.first()
        return first_image.image.url if first_image else ''

    @property
    def stock_status(self):
        if not self.stock_available or self.quantity == 0:
            return 'Stock Not Available'
        return 'In Stock'


class OnamSareeImage(models.Model):
    saree = models.ForeignKey(OnamSaree, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField('image', folder='onam_sarees')

    def __str__(self):
        return f"Image for {self.saree.collection_name}"


class OnamSetMund(models.Model):
    collection_name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    stock_available = models.BooleanField(default=True)

    class Meta:
        db_table = 'shop_by_collection'
        verbose_name = 'SHOP BY COLLECTION'
        verbose_name_plural = 'SHOP BY COLLECTION'

    def __str__(self):
        return self.collection_name

    @property
    def first_image_url(self):
        first_image = self.images.first()
        return first_image.image.url if first_image else ''

    @property
    def stock_status(self):
        if not self.stock_available or self.quantity == 0:
            return 'Stock Not Available'
        return 'In Stock'


class OnamSetMundImage(models.Model):
    mund = models.ForeignKey(OnamSetMund, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField('image', folder='onam_munds')

    class Meta:
        db_table = 'product_onammundimage'
        verbose_name = 'Onam Set-Mund Image'
        verbose_name_plural = 'Onam Set-Mund Images'

    def __str__(self):
        return f"Image for {self.mund.collection_name}"


class ColoredSaree(models.Model):
    collection_name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    stock_available = models.BooleanField(default=True)

    class Meta:
        db_table = 'most_purchased_sarees'
        verbose_name = 'MOST PURCHASED SAREE'
        verbose_name_plural = 'MOST PURCHASED SAREES'

    def __str__(self):
        return self.collection_name

    @property
    def first_image_url(self):
        first_image = self.images.first()
        return first_image.image.url if first_image else ''

    @property
    def stock_status(self):
        if not self.stock_available or self.quantity == 0:
            return 'Stock Not Available'
        return 'In Stock'


class ColoredSareeImage(models.Model):
    saree = models.ForeignKey(ColoredSaree, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField('image', folder='colored_sarees')

    class Meta:
        verbose_name = 'Colored Saree Image'
        verbose_name_plural = 'Colored Saree Images'

    def __str__(self):
        return f"Image for {self.saree.collection_name}"


class SiteUser(models.Model):
    name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
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

class Order(models.Model):
    user = models.ForeignKey(SiteUser, on_delete=models.CASCADE, related_name='orders')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=50, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
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

