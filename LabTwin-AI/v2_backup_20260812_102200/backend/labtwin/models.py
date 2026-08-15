from django.db import models


class StudentProfile(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ConceptProgress(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="concept_progress"
    )

    concept_key = models.CharField(max_length=100)

    attempts = models.IntegerField(default=0)
    mastered = models.IntegerField(default=0)
    failures = models.IntegerField(default=0)

    misconception_count = models.IntegerField(default=0)

    last_misconception = models.TextField(
        blank=True,
        default=""
    )

    total_score = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "student",
            "concept_key"
        )

    def __str__(self):
        return f"{self.student.name} - {self.concept_key}"

    @property
    def average_score(self):
        if self.attempts == 0:
            return 0

        return round(
            self.total_score / self.attempts,
            1
        )


class Attempt(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    question = models.TextField()

    concept_key = models.CharField(
        max_length=100,
        default="OTHER"
    )

    initial_score = models.FloatField(
        default=0
    )

    final_score = models.FloatField(
        null=True,
        blank=True
    )

    viva_score = models.FloatField(
        null=True,
        blank=True
    )

    misconception = models.TextField(
        blank=True,
        default=""
    )

    status = models.CharField(
        max_length=50,
        default="Attempted"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.student.name} - {self.concept_key}"
