from django.db import models

class Medicine(models.Model):
    name = models.CharField(max_length=150)
    strength = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "strength"]
        constraints = [models.UniqueConstraint(fields=["name", "strength"], name="unique_medicine_strength")]

    def __str__(self):
        return f"{self.name} ({self.strength})"
