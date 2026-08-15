import json

from django.db.models import Avg, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import (
    StudentProfile,
    ConceptProgress,
    TopicProgress,
    Attempt,
)


def _weighted_average(values):
    """
    Recent evidence matters more than older evidence.
    Input must already be ordered oldest -> newest.
    """
    clean = [
        float(value)
        for value in values
        if value is not None
    ]

    if not clean:
        return 0.0

    weights = list(range(1, len(clean) + 1))

    return sum(
        value * weight
        for value, weight in zip(clean, weights)
    ) / sum(weights)


def _hint_independence_score(level):
    """
    0 hints -> 100
    1 hint  -> 70
    2 hints -> 40
    3+      -> 10
    """
    try:
        level = max(0, int(level))
    except Exception:
        level = 0

    return max(
        10,
        100 - (30 * level),
    )


def recalculate_topic_progress(student, topic):
    """
    Rebuild exact-topic mastery from the student's recent evidence.

    LLMs describe misconceptions and evaluate which rubric concepts
    are present. Django owns the numeric mastery decision.
    """
    attempts = list(
        Attempt.objects.filter(
            student=student,
            topic=topic,
        )
        .order_by("created_at")
    )

    if not attempts:
        return None

    # Keep one final record per programming question. This protects
    # mastery from accidental double-clicks or repeated save requests.
    unique_attempts = {}

    for attempt in attempts:
        key = (
            attempt.topic.strip(),
            attempt.question.strip(),
        )
        unique_attempts[key] = attempt

    attempts = sorted(
        unique_attempts.values(),
        key=lambda item: item.created_at,
    )

    recent = attempts[-5:]

    initial_average = _weighted_average(
        [
            attempt.initial_score
            for attempt in recent
        ]
    )

    final_average = _weighted_average(
        [
            (
                attempt.final_score
                if attempt.final_score is not None
                else attempt.initial_score
            )
            for attempt in recent
        ]
    )

    viva_values = [
        attempt.viva_score
        for attempt in recent
        if attempt.viva_score is not None
    ]

    viva_average = _weighted_average(
        viva_values
    )

    hint_average = _weighted_average(
        [
            attempt.hint_level
            for attempt in recent
        ]
    )

    independence_average = _weighted_average(
        [
            _hint_independence_score(
                attempt.hint_level
            )
            for attempt in recent
        ]
    )

    verification_passed = any(
        attempt.verification
        and attempt.initial_score >= 80
        and (
            attempt.final_score is None
            or attempt.final_score >= 80
        )
        and attempt.viva_score is not None
        and attempt.viva_score >= 70
        and attempt.hint_level <= 1
        for attempt in attempts
    )

    verification_score = (
        100
        if verification_passed
        else 0
    )

    # Personalized topic mastery evidence:
    #
    # 35% independent/first-attempt coding
    # 25% conceptual viva understanding
    # 15% corrected/final coding ability
    # 15% independent verification
    # 10% hint independence
    mastery = (
        (0.35 * initial_average)
        + (0.25 * viva_average)
        + (0.15 * final_average)
        + (0.15 * verification_score)
        + (0.10 * independence_average)
    )

    # Missing viva evidence or missing independent verification
    # can never silently become mastery.
    if not viva_values:
        mastery = min(
            mastery,
            69.0,
        )

    if not verification_passed:
        mastery = min(
            mastery,
            79.0,
        )

    mastery = round(
        max(
            0,
            min(
                100,
                mastery,
            ),
        ),
        1,
    )

    latest = attempts[-1]

    latest_final = (
        latest.final_score
        if latest.final_score is not None
        else latest.initial_score
    )

    latest_viva = (
        latest.viva_score
        if latest.viva_score is not None
        else 0
    )

    if latest_final < 80:
        status = "Needs Coding Practice"

    elif latest_viva < 40:
        status = "Needs Practice"

    elif latest_viva < 70:
        status = "Needs Verification"

    elif not verification_passed:
        status = "Needs Verification"

    elif mastery >= 80:
        status = "Mastered"

    else:
        status = "Developing"

    misconceptions = [
        attempt.misconception.strip()
        for attempt in attempts
        if attempt.misconception.strip()
    ]

    progress, _ = TopicProgress.objects.get_or_create(
        student=student,
        topic=topic,
        defaults={
            "concept_key":
                latest.concept_key,
        },
    )

    progress.concept_key = latest.concept_key
    progress.attempts = len(attempts)
    progress.mastery_score = mastery
    progress.status = status

    progress.verification_passed = (
        verification_passed
    )

    progress.verification_required = (
        status != "Mastered"
    )

    progress.misconception_count = len(
        misconceptions
    )

    progress.last_misconception = (
        misconceptions[-1]
        if misconceptions
        else ""
    )

    progress.average_hint_level = round(
        hint_average,
        1,
    )

    progress.save()

    Attempt.objects.filter(
        id=latest.id
    ).update(
        mastery_score=mastery
    )

    return progress


def _update_broad_concept_progress(
    student,
    concept_key,
):
    """
    Keep the original ConceptProgress table updated so old parts of
    the project remain compatible.
    """
    attempts = Attempt.objects.filter(
        student=student,
        concept_key=concept_key,
    )

    progress, _ = ConceptProgress.objects.get_or_create(
        student=student,
        concept_key=concept_key,
    )

    progress.attempts = attempts.count()

    progress.failures = attempts.filter(
        initial_score__lt=100,
    ).count()

    progress.mastered = TopicProgress.objects.filter(
        student=student,
        concept_key=concept_key,
        status="Mastered",
    ).count()

    progress.misconception_count = attempts.exclude(
        misconception="",
    ).count()

    latest_with_misconception = (
        attempts.exclude(
            misconception="",
        )
        .order_by("-created_at")
        .first()
    )

    progress.last_misconception = (
        latest_with_misconception.misconception
        if latest_with_misconception
        else ""
    )

    scores = [
        (
            attempt.final_score
            if attempt.final_score is not None
            else attempt.initial_score
        )
        for attempt in attempts
    ]

    progress.total_score = sum(scores)

    progress.save()


def _dashboard_payload(student):
    attempts = Attempt.objects.filter(
        student=student
    )

    topic_rows = TopicProgress.objects.filter(
        student=student
    ).order_by(
        "mastery_score",
        "-updated_at",
    )

    # Count completed unique programming questions, not raw save rows.
    questions_attempted = attempts.values(
        "question"
    ).distinct().count()

    mastered_count = topic_rows.filter(
        status="Mastered"
    ).count()

    average_initial = attempts.aggregate(
        average=Avg("initial_score")
    )["average"] or 0

    # Use the uploaded syllabus to measure coverage.
    try:
        from .views import load_state

        state = load_state()

        syllabus_topics = [
            str(topic).strip()
            for topic in state.get(
                "topics",
                []
            )
            if str(topic).strip()
        ]

    except Exception:
        syllabus_topics = []

    unique_syllabus_topics = list(
        dict.fromkeys(
            syllabus_topics
        )
    )

    tested_topic_names = {
        row.topic
        for row in topic_rows
    }

    if unique_syllabus_topics:
        covered = sum(
            1
            for topic in unique_syllabus_topics
            if topic in tested_topic_names
        )

        coverage = (
            covered
            / len(unique_syllabus_topics)
            * 100
        )

    else:
        # If the source had explicit questions rather than a clean
        # topic list, use tested-topic count as available evidence.
        coverage = (
            100
            if questions_attempted > 0
            else 0
        )

    tested_mastery = (
        topic_rows.aggregate(
            average=Avg("mastery_score")
        )["average"]
        or 0
    )

    # Overall readiness separates "how well tested topics are known"
    # from "how much of the syllabus has actually been covered".
    readiness = round(
        (0.60 * tested_mastery)
        + (0.40 * coverage),
        1,
    )

    weakest_topic = None

    for row in topic_rows:
        if row.status != "Mastered":
            weakest_topic = {
                "topic": row.topic,
                "concept_key":
                    row.concept_key,
                "mastery_score":
                    round(
                        row.mastery_score,
                        1,
                    ),
                "status":
                    row.status,
                "attempts":
                    row.attempts,
                "verification_required":
                    row.verification_required,
                "verification_passed":
                    row.verification_passed,
                "misconception_count":
                    row.misconception_count,
                "last_misconception":
                    row.last_misconception,
                "average_hint_level":
                    row.average_hint_level,
            }
            break

    topics = [
        {
            "topic":
                row.topic,
            "concept_key":
                row.concept_key,
            "attempts":
                row.attempts,
            "mastery_score":
                round(
                    row.mastery_score,
                    1,
                ),
            "status":
                row.status,
            "verification_required":
                row.verification_required,
            "verification_passed":
                row.verification_passed,
            "misconception_count":
                row.misconception_count,
            "last_misconception":
                row.last_misconception,
            "average_hint_level":
                row.average_hint_level,
        }
        for row in topic_rows
    ]

    recent_attempts = [
        {
            "question":
                attempt.question,
            "topic":
                attempt.topic,
            "concept_key":
                attempt.concept_key,
            "initial_score":
                attempt.initial_score,
            "final_score":
                attempt.final_score,
            "viva_score":
                attempt.viva_score,
            "hint_level":
                attempt.hint_level,
            "verification":
                attempt.verification,
            "status":
                attempt.status,
            "misconception":
                attempt.misconception,
            "mastery_score":
                attempt.mastery_score,
        }
        for attempt in attempts.order_by(
            "-created_at"
        )[:5]
    ]

    # Compatibility object for any old UI still expecting
    # weakest_concept.
    weakest_concept = None

    if weakest_topic:
        weakest_concept = {
            "concept_key":
                weakest_topic[
                    "concept_key"
                ],
            "average_score":
                weakest_topic[
                    "mastery_score"
                ],
            "last_misconception":
                weakest_topic[
                    "last_misconception"
                ],
        }

    return {
        "student": {
            "id":
                student.id,
            "name":
                student.name,
        },
        "questions_attempted":
            questions_attempted,
        "mastered":
            mastered_count,
        "average_initial_score":
            round(
                average_initial,
                1,
            ),
        "topic_mastery_average":
            round(
                tested_mastery,
                1,
            ),
        "syllabus_coverage":
            round(
                coverage,
                1,
            ),
        "lab_readiness":
            readiness,
        "weakest_topic":
            weakest_topic,
        "weakest_concept":
            weakest_concept,
        "topics":
            topics,
        "recent_attempts":
            recent_attempts,
    }


@csrf_exempt
def start_student(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        name = data.get(
            "name",
            "",
        ).strip()

        mode = data.get(
            "mode",
            "new",
        )

        if not name:
            return JsonResponse(
                {
                    "error":
                        "Student name is required"
                },
                status=400,
            )

        if mode == "new":
            student = StudentProfile.objects.create(
                name=name
            )

            return JsonResponse({
                "student_id":
                    student.id,
                "name":
                    student.name,
                "mode":
                    "new",
                "message":
                    "New learning session created.",
            })

        existing = (
            StudentProfile.objects.filter(
                name__iexact=name
            )
            .annotate(
                attempt_count=Count(
                    "attempts"
                )
            )
            .order_by(
                "-attempt_count",
                "-created_at",
            )
            .first()
        )

        if not existing:
            return JsonResponse(
                {
                    "error":
                        "No previous student profile found with this name."
                },
                status=404,
            )

        return JsonResponse({
            "student_id":
                existing.id,
            "name":
                existing.name,
            "mode":
                "continue",
            "message":
                "Previous progress loaded.",
        })

    except Exception as error:
        return JsonResponse(
            {"error": str(error)},
            status=500,
        )


@csrf_exempt
def save_attempt(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        student = StudentProfile.objects.get(
            id=data.get(
                "student_id"
            )
        )

        topic = (
            data.get(
                "topic",
                "",
            ).strip()
            or "General"
        )

        concept_key = (
            data.get(
                "concept_key",
                "OTHER",
            )
            or "OTHER"
        )

        initial_score = float(
            data.get(
                "initial_score",
                0,
            )
            or 0
        )

        final_score = data.get(
            "final_score"
        )

        viva_score = data.get(
            "viva_score"
        )

        misconception = (
            data.get(
                "misconception",
                "",
            )
            or ""
        ).strip()

        status = (
            data.get(
                "status",
                "Attempted",
            )
            or "Attempted"
        )

        question = (
            data.get(
                "question",
                "",
            )
            or ""
        )

        hint_level = int(
            data.get(
                "hint_level",
                0,
            )
            or 0
        )

        hint_level = max(
            0,
            min(
                3,
                hint_level,
            ),
        )

        verification = bool(
            data.get(
                "verification",
                False,
            )
        )

        final_score_value = (
            float(final_score)
            if final_score is not None
            else None
        )

        viva_score_value = (
            float(viva_score)
            if viva_score is not None
            else None
        )

        independent = (
            initial_score >= 80
            and hint_level == 0
        )

        # Idempotent memory save: one record per student/topic/question.
        # If the browser retries or the button is clicked twice, update
        # the same evidence instead of inflating attempts/mastery.
        duplicates = Attempt.objects.filter(
            student=student,
            topic=topic,
            question=question,
        ).order_by(
            "-created_at"
        )

        attempt = duplicates.first()

        if attempt:
            duplicates.exclude(
                id=attempt.id
            ).delete()

            attempt.concept_key = concept_key
            attempt.initial_score = initial_score
            attempt.final_score = final_score_value
            attempt.viva_score = viva_score_value
            attempt.misconception = misconception
            attempt.status = status
            attempt.hint_level = hint_level
            attempt.verification = verification
            attempt.independent = independent
            attempt.save()

        else:
            attempt = Attempt.objects.create(
                student=student,
                question=question,
                topic=topic,
                concept_key=concept_key,
                initial_score=initial_score,
                final_score=final_score_value,
                viva_score=viva_score_value,
                misconception=misconception,
                status=status,
                hint_level=hint_level,
                verification=verification,
                independent=independent,
            )

        topic_progress = (
            recalculate_topic_progress(
                student,
                topic,
            )
        )

        _update_broad_concept_progress(
            student,
            concept_key,
        )

        dashboard = _dashboard_payload(
            student
        )

        return JsonResponse({
            "success":
                True,
            "attempt_id":
                attempt.id,
            "topic_progress": {
                "topic":
                    topic_progress.topic,
                "mastery_score":
                    topic_progress.mastery_score,
                "status":
                    topic_progress.status,
                "verification_required":
                    topic_progress.verification_required,
                "verification_passed":
                    topic_progress.verification_passed,
                "misconception_count":
                    topic_progress.misconception_count,
                "average_hint_level":
                    topic_progress.average_hint_level,
            },
            "dashboard":
                dashboard,
        })

    except StudentProfile.DoesNotExist:
        return JsonResponse(
            {"error": "Student not found"},
            status=404,
        )

    except Exception as error:
        return JsonResponse(
            {"error": str(error)},
            status=500,
        )


def progress_dashboard(request):

    student_id = request.GET.get(
        "student_id"
    )

    if not student_id:
        return JsonResponse(
            {
                "error":
                    "student_id required"
            },
            status=400,
        )

    try:
        student = StudentProfile.objects.get(
            id=student_id
        )

        return JsonResponse(
            _dashboard_payload(
                student
            )
        )

    except StudentProfile.DoesNotExist:
        return JsonResponse(
            {"error": "Student not found"},
            status=404,
        )
