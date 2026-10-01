from django.db.models.signals import post_save
from django.dispatch import receiver

from billing.models import Payment

from .models import FEE_INCOME, BusinessTransaction, Category


@receiver(post_save, sender=Payment)
def post_fee_payment(sender, instance, created, **kwargs):
    """Every fee payment (including transfers from trust) lands in the business account."""
    if not created:
        return
    category, _ = Category.objects.get_or_create(name=FEE_INCOME, defaults={"kind": Category.INCOME, "system": True})
    invoice = instance.invoice
    BusinessTransaction.objects.create(
        date=instance.date, type=BusinessTransaction.RECEIPT, category=category,
        party=invoice.matter.client.name,
        description=f"Payment of {invoice.number} ({instance.get_method_display()})",
        reference=instance.reference, amount=instance.amount, payment=instance, created_by=instance.created_by,
    )
