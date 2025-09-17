import uuid
from django.db import models
from django.utils.timezone import now


class EventLog(models.Model):
    EVENT_TYPE_CHOICES = [
        ('user_query', 'User Query'),
        ('research_lab', 'Research Lab'),
    ]

    session_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    event_type = models.CharField(
        max_length=50, choices=EVENT_TYPE_CHOICES, default='user_query'
    )
    user_input = models.JSONField(default=dict)
    generated_result = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=now, editable=False)
    algorithm_version = models.CharField(max_length=22, default='v1.0.1')

    def __str__(self):
        return f"{self.event_type} - {self.session_id}"
