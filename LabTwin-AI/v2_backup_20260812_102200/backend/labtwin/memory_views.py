import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Avg

from .models import (
    StudentProfile,
    ConceptProgress,
    Attempt,
)


@csrf_exempt
def start_student(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(request.body)

        name = data.get("name", "").strip()

        mode = data.get(
            "mode",
            "new"
        )

        if not name:
            return JsonResponse(
                {"error": "Student name is required"},
                status=400
            )

        # -----------------------------------
        # NEW SESSION
        # Always create fresh student profile
        # -----------------------------------

        if mode == "new":

            student = StudentProfile.objects.create(
                name=name
            )

            return JsonResponse({
                "student_id": student.id,
                "name": student.name,
                "mode": "new",
                "message": "New learning session created."
            })


        # -----------------------------------
        # CONTINUE EXISTING PROFILE
        # -----------------------------------

        existing = StudentProfile.objects.filter(
            name__iexact=name
        ).order_by("-created_at").first()

        if not existing:

            return JsonResponse(
                {
                    "error":
                    "No previous student profile found with this name."
                },
                status=404
            )

        return JsonResponse({
            "student_id": existing.id,
            "name": existing.name,
            "mode": "continue",
            "message": "Previous progress loaded."
        })


    except Exception as error:

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


@csrf_exempt
def save_attempt(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:

        data = json.loads(request.body)

        student_id = data.get("student_id")

        student = StudentProfile.objects.get(
            id=student_id
        )

        concept_key = data.get(
            "concept_key",
            "OTHER"
        )

        initial_score = float(
            data.get(
                "initial_score",
                0
            )
        )

        final_score = data.get(
            "final_score"
        )

        viva_score = data.get(
            "viva_score"
        )

        misconception = data.get(
            "misconception",
            ""
        ) or ""

        status = data.get(
            "status",
            "Attempted"
        )

        question = data.get(
            "question",
            ""
        )


        attempt = Attempt.objects.create(

            student=student,

            question=question,

            concept_key=concept_key,

            initial_score=initial_score,

            final_score=(
                float(final_score)
                if final_score is not None
                else None
            ),

            viva_score=(
                float(viva_score)
                if viva_score is not None
                else None
            ),

            misconception=misconception,

            status=status
        )


        progress, created = ConceptProgress.objects.get_or_create(

            student=student,

            concept_key=concept_key

        )


        progress.attempts += 1

        score_for_memory = (
            float(final_score)
            if final_score is not None
            else initial_score
        )

        progress.total_score += score_for_memory


        if status in [
            "Mastered",
            "Corrected"
        ]:
            progress.mastered += 1


        if initial_score < 100:
            progress.failures += 1


        if misconception:
            progress.misconception_count += 1
            progress.last_misconception = misconception


        progress.save()


        return JsonResponse({
            "success": True,
            "attempt_id": attempt.id
        })


    except StudentProfile.DoesNotExist:

        return JsonResponse(
            {"error": "Student not found"},
            status=404
        )

    except Exception as error:

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


def progress_dashboard(request):

    student_id = request.GET.get(
        "student_id"
    )

    if not student_id:

        return JsonResponse(
            {"error": "student_id required"},
            status=400
        )


    try:

        student = StudentProfile.objects.get(
            id=student_id
        )

        attempts = Attempt.objects.filter(
            student=student
        )

        concept_rows = ConceptProgress.objects.filter(
            student=student
        )


        questions_attempted = attempts.count()


        mastered_count = attempts.filter(
            status__in=[
                "Mastered",
                "Corrected"
            ]
        ).count()


        average_initial = attempts.aggregate(
            average=Avg("initial_score")
        )["average"] or 0


        # --------------------------------------------------
        # LAB READINESS
        #
        # 40% final coding performance
        # 25% viva / understanding
        # 20% first-attempt coding performance
        # 15% mastery consistency
        # --------------------------------------------------

        final_scores = [
            attempt.final_score
            if attempt.final_score is not None
            else attempt.initial_score
            for attempt in attempts
        ]

        viva_scores = [
            attempt.viva_score
            for attempt in attempts
            if attempt.viva_score is not None
        ]

        if attempts.exists():

            final_average = (
                sum(final_scores) /
                len(final_scores)
            )

            initial_average = (
                sum(
                    attempt.initial_score
                    for attempt in attempts
                ) /
                attempts.count()
            )

            # If a direct-correct answer had no viva,
            # do not unfairly penalize the student.
            viva_average = (
                sum(viva_scores) /
                len(viva_scores)
                if viva_scores
                else final_average
            )

            mastery_ratio = (
                mastered_count /
                attempts.count()
            ) * 100

            readiness = round(
                (0.40 * final_average)
                + (0.25 * viva_average)
                + (0.20 * initial_average)
                + (0.15 * mastery_ratio),
                1
            )

        else:

            readiness = 0


        concepts = []
        weakest = None


        for row in concept_rows:

            item = {
                "concept_key": row.concept_key,
                "attempts": row.attempts,
                "mastered": row.mastered,
                "failures": row.failures,
                "average_score": row.average_score,
                "misconception_count": row.misconception_count,
                "last_misconception": row.last_misconception
            }

            concepts.append(item)

            if (
                row.attempts > 0
                and row.average_score < 80
                and (
                    weakest is None
                    or row.average_score
                    < weakest["average_score"]
                )
            ):
                weakest = item


        recent_attempts = [
            {
                "question": attempt.question,
                "concept_key": attempt.concept_key,
                "initial_score": attempt.initial_score,
                "final_score": attempt.final_score,
                "status": attempt.status,
                "misconception": attempt.misconception
            }

            for attempt in attempts.order_by(
                "-created_at"
            )[:5]
        ]


        return JsonResponse({

            "student": {
                "id": student.id,
                "name": student.name
            },

            "questions_attempted":
                questions_attempted,

            "mastered":
                mastered_count,

            "average_initial_score":
                round(
                    average_initial,
                    1
                ),

            "lab_readiness":
                readiness,

            "weakest_concept":
                weakest,

            "concepts":
                concepts,

            "recent_attempts":
                recent_attempts
        })


    except StudentProfile.DoesNotExist:

        return JsonResponse(
            {"error": "Student not found"},
            status=404
        )
