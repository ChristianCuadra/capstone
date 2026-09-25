from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    # CreateExtension no hace nada en bases que no son PostgreSQL (p. ej. SQLite local).
    operations = [VectorExtension()]
