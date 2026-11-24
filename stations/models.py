from django.db import models


class Station(models.Model):
    """A US fuel stop with its retail diesel price and (city-level) coordinates."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=5)  # USD per gallon
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["opis_id"]
        indexes = [models.Index(fields=["latitude", "longitude"])]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price:.3f}"


class City(models.Model):
    """US city centroid, used to turn 'Dallas, TX' into coordinates without an API call."""

    key = models.CharField(max_length=120)  # normalized name, see ingest.normalize_city
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "state"], name="uniq_city_key_state")]
