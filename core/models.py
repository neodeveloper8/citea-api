# Create your models here.
# core/models.py
from django.db import models


class TimeStampedModel(models.Model):
    """Base abstracta: añade created_at / updated_at a cualquier modelo que herede."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
