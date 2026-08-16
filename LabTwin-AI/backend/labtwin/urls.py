from django.urls import path

from .views import (
    upload_syllabus,
    next_question,
    analyze_code,
    tutor_help,
    evaluate_code,
    student_session,
)

from .memory_views import (
    start_student,
    save_attempt,
    progress_dashboard,
)

from .adaptive_views import (
    adaptive_next_question,
)

from .hint_views import (
    progressive_hint,
)


urlpatterns = [

    path(
        "start-student/",
        start_student
    ),

    path(
        "save-attempt/",
        save_attempt
    ),

    path(
        "progress/",
        progress_dashboard
    ),

    path(
        "student-session/",
        student_session
    ),

    path(
        "upload-syllabus/",
        upload_syllabus
    ),

    path(
        "next-question/",
        next_question
    ),

    path(
        "adaptive-next-question/",
        adaptive_next_question
    ),

    path(
        "analyze/",
        analyze_code
    ),

    path(
        "tutor/",
        tutor_help
    ),

    path(
        "progressive-hint/",
        progressive_hint
    ),

    path(
        "evaluate/",
        evaluate_code
    ),
]
