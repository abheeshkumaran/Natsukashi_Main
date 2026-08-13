import json
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from product.models import Category, ProductImage, UpdationTask

EXPORT_PATH = Path(__file__).resolve().parents[3] / 'deploy' / 'cloudinary_media_export.json'


class Command(BaseCommand):
    """One-off: re-uploads images captured from Cloudinary (before the
    CloudinaryField -> ImageField cutover) into the now-configured S3
    storage. Reads deploy/cloudinary_media_export.json, which was generated
    while CloudinaryField was still active - that file is the only record
    of where each image used to live, so this must be run with that file
    present and AWS_* env vars already set to the real bucket.

    Safe to re-run: skips any row whose field is already populated, so an
    interrupted run can just be re-run to pick up where it left off.

    Usage: python manage.py migrate_media_to_s3
    """
    help = 'Downloads images from the Cloudinary export and re-uploads them to S3'

    def handle(self, *args, **options):
        if not EXPORT_PATH.exists():
            raise CommandError(f'{EXPORT_PATH} not found - nothing to migrate.')

        with open(EXPORT_PATH) as f:
            export = json.load(f)

        self._migrate_categories(export.get('categories', []))
        self._migrate_product_images(export.get('product_images', []))
        self._migrate_updation_tasks(export.get('updation_tasks', []))

    def _download(self, url):
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        filename = Path(urlparse(url).path).name or 'image.jpg'
        return filename, response.content

    def _migrate_categories(self, entries):
        for entry in entries:
            obj = Category.objects.filter(pk=entry['pk']).first()
            if not obj or obj.image:
                continue
            try:
                filename, content = self._download(entry['url'])
                obj.image.save(filename, ContentFile(content), save=True)
                self.stdout.write(self.style.SUCCESS(f"Category #{entry['pk']} ({entry.get('name', '')}) migrated"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Category #{entry['pk']} failed: {e}"))

    def _migrate_product_images(self, entries):
        for entry in entries:
            obj = ProductImage.objects.filter(pk=entry['pk']).first()
            if not obj or obj.image:
                continue
            try:
                filename, content = self._download(entry['url'])
                obj.image.save(filename, ContentFile(content), save=True)
                self.stdout.write(self.style.SUCCESS(f"ProductImage #{entry['pk']} migrated"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"ProductImage #{entry['pk']} failed: {e}"))

    def _migrate_updation_tasks(self, entries):
        for entry in entries:
            obj = UpdationTask.objects.filter(pk=entry['pk']).first()
            if not obj or obj.related_image:
                continue
            try:
                filename, content = self._download(entry['url'])
                obj.related_image.save(filename, ContentFile(content), save=True)
                self.stdout.write(self.style.SUCCESS(f"UpdationTask #{entry['pk']} migrated"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"UpdationTask #{entry['pk']} failed: {e}"))
