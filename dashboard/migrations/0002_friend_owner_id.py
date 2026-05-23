# This migration is intentionally empty — the owner_id field was added
# directly to the initial migration since the database had no data yet.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0001_initial")]
    operations = []
