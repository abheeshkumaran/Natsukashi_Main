from django.db import models
from cloudinary.models import CloudinaryField


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
