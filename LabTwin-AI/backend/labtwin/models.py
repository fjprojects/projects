from django.db import models


class StudentProfile(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ConceptProgress(models.Model):
    """
    Broad concept memory kept for compatibility and high-level analytics.
    Example concept_key values: POINTERS, ARRAYS, FUNCTIONS.
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="concept_progress",
    )

    concept_key = models.CharField(max_length=100)

    attempts = models.IntegerField(default=0)
    mastered = models.IntegerField(default=0)
    failures = models.IntegerField(default=0)

    misconception_count = models.IntegerField(default=0)

    last_misconception = models.TextField(
        blank=True,
        default="",
    )

    total_score = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "student",
            "concept_key",
        )

    def __str__(self):
        return f"{self.student.name} - {self.concept_key}"

    @property
    def average_score(self):
        if self.attempts == 0:
            return 0

        return round(
            self.total_score / self.attempts,
            1,
        )


class TopicProgress(models.Model):
    """
    Exact syllabus-topic memory.

    This is the main personalization layer used by LabTwin V2.
    Example topic: "Pointer to Function"
    Broad concept: "POINTERS"
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="topic_progress",
    )

    topic = models.CharField(max_length=200)
    concept_key = models.CharField(
        max_length=100,
        default="OTHER",
    )

    attempts = models.IntegerField(default=0)

    mastery_score = models.FloatField(default=0)

    status = models.CharField(
        max_length=50,
        default="Not Tested",
    )

    verification_required = models.BooleanField(default=False)
    verification_passed = models.BooleanField(default=False)

    misconception_count = models.IntegerField(default=0)

    last_misconception = models.TextField(
        blank=True,
        default="",
    )

    average_hint_level = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "student",
            "topic",
        )

    def __str__(self):
        return f"{self.student.name} - {self.topic}"


class Attempt(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    question = models.TextField()

    topic = models.CharField(
        max_length=200,
        default="General",
    )

    concept_key = models.CharField(
        max_length=100,
        default="OTHER",
    )

    initial_score = models.FloatField(
        default=0,
    )

    final_score = models.FloatField(
        null=True,
        blank=True,
    )

    viva_score = models.FloatField(
        null=True,
        blank=True,
    )

    misconception = models.TextField(
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=50,
        default="Attempted",
    )

    # 0 = independent, 1 = light hint, 2 = structural hint,
    # 3 = near-solution guidance.
    hint_level = models.IntegerField(default=0)

    # True only when this question was intentionally generated as
    # an independent verification problem for a previously weak topic.
    verification = models.BooleanField(default=False)

    independent = models.BooleanField(default=False)

    mastery_score = models.FloatField(default=0)

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.student.name} - {self.topic}"
