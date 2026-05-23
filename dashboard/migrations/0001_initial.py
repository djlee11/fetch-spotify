from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Friend",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_id", models.CharField(max_length=255, db_index=True)),
                ("user_id", models.CharField(max_length=255)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["added_at"],
                "unique_together": {("owner_id", "user_id")},
            },
        ),
    ]
