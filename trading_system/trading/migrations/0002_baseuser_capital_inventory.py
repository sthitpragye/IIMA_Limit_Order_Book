from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='baseuser',
            name='capital',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='baseuser',
            name='inventory',
            field=models.IntegerField(default=0),
        ),
    ]
