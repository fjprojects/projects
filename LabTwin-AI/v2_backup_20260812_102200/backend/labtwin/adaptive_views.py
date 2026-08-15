import json
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crewai import Agent, Task, Crew, Process

from .models import StudentProfile, ConceptProgress, Attempt

from .views import (
    load_state,
    save_state,
    llm,
    clean_json_output,
    generate_tests_for_question,
)


adaptive_agent = Agent(
    role="Adaptive Lab Question Planner",
    goal=(
        "Select and generate the best next programming lab question "
        "based on the uploaded syllabus, programming language, and "
        "student weaknesses."
    ),
    backstory=(
        "You are a university programming lab instructor. "
        "You never convert language-specific concepts into another language. "
        "C concepts remain C, Java concepts remain Java, and Python concepts remain Python."
    ),
    llm=llm,
    verbose=False
)


def get_weakest_concept(student_id):

    if not student_id:
        return None

    try:
        rows = ConceptProgress.objects.filter(
            student_id=student_id
        )

        state = load_state()
        history = state.get("history", [])

        verification_candidates = []
        weak_candidates = []

        for row in rows:

            average = row.average_score

            latest_attempt = (
                Attempt.objects.filter(
                    student_id=student_id,
                    concept_key=row.concept_key
                )
                .order_by("-created_at")
                .first()
            )

            exact_topic = None
            last_misconception = row.last_misconception or ""

            if latest_attempt:
                latest_problem = (latest_attempt.question or "").strip()

                for item in reversed(history):
                    if (
                        item.get("concept_key") == row.concept_key
                        and item.get("problem", "").strip() == latest_problem
                    ):
                        exact_topic = item.get("topic")
                        break

            candidate = {
                "concept_key": row.concept_key,
                "exact_topic": exact_topic,
                "average_score": average,
                "failures": row.failures,
                "mastered": row.mastered,
                "last_misconception": last_misconception,
            }

            # A failed concept must be independently verified.
            # Correcting the same original question is not enough.
            if (
                row.failures > 0
                and row.mastered <= row.failures
            ):
                candidate["reason"] = "verification"
                verification_candidates.append(candidate)

            elif average < 80:
                candidate["reason"] = "weakness"
                weak_candidates.append(candidate)

        if verification_candidates:

            verification_candidates.sort(
                key=lambda item: (
                    -item["failures"],
                    item["mastered"],
                    item["average_score"]
                )
            )

            return verification_candidates[0]

        if weak_candidates:

            weak_candidates.sort(
                key=lambda item:
                    item["average_score"]
            )

            return weak_candidates[0]

        return None

    except Exception as error:

        print(
            "Adaptive memory lookup error:",
            error
        )

        return None


def generate_adaptive_question(
    topics,
    history,
    language,
    weak_concept=None
):

    previous_questions = [

        item.get("problem", "")

        for item in history[-10:]

    ]


    weakness_instruction = ""

    if weak_concept:

        exact_topic = weak_concept.get("exact_topic")
        concept_key = weak_concept.get("concept_key", "OTHER")
        reason = weak_concept.get("reason", "weakness")
        misconception = weak_concept.get("last_misconception", "")

        if exact_topic and reason == "verification":
            weakness_instruction = f"""
THIS IS A REQUIRED VERIFICATION QUESTION.

Broad concept:
{concept_key}

Exact unresolved syllabus topic:
{exact_topic}

Previous misconception:
{misconception}

You MUST generate a DIFFERENT problem that directly tests the
EXACT topic "{exact_topic}".

Do NOT switch to another topic even if it belongs to the same
broad concept category.

The new problem must not repeat the previous question.
"""
        elif exact_topic:
            weakness_instruction = f"""
STUDENT'S CURRENT WEAKNESS:

Broad concept:
{concept_key}

Exact syllabus topic:
{exact_topic}

Previous misconception:
{misconception}

Prefer a new problem that directly reinforces "{exact_topic}".
Do not repeat the previous question.
"""
        else:
            weakness_instruction = f"""
STUDENT'S CURRENT WEAK CONCEPT:

{concept_key}

Previous misconception:
{misconception}

Generate a new question that reinforces this concept while
remaining strictly inside the uploaded syllabus.

Do not repeat the previous question.
"""


    if language == "C":

        language_rules = """
THIS IS A C PROGRAMMING SYLLABUS.

Generate a genuine C programming problem.

Important examples:

- Pointer to Function means actual C function pointers,
  such as int (*ptr)(int, int).

- Pointer to Pointer means actual ** pointer usage.

- Pointer to Structure means struct pointers and -> operator.

- Dynamic Memory Allocation means malloc, calloc,
  realloc or free where appropriate.

- File Handling means actual C FILE pointers and
  fopen/fclose/fread/fwrite/etc.

NEVER convert these concepts into Python dictionaries,
Python functions, Java objects, or another language.

The student must write C code.
"""

    elif language == "Java":

        language_rules = """
THIS IS A JAVA PROGRAMMING SYLLABUS.

Generate genuine Java questions.

The submitted program should use:

public class Main

and:

public static void main(String[] args)

Do not translate Java-specific concepts into Python or C.
"""

    else:

        language_rules = """
THIS IS A PYTHON PROGRAMMING SYLLABUS.

Generate genuine Python questions using standard Python.
"""


    task = Task(
        description=f"""
Generate ONE NEW adaptive programming lab question.

PROGRAMMING LANGUAGE:

{language}

UPLOADED SYLLABUS TOPICS:

{json.dumps(topics, indent=2)}

PREVIOUS QUESTIONS:

{json.dumps(previous_questions, indent=2)}

{weakness_instruction}

{language_rules}

STRICT RULES:

1. Stay strictly inside the uploaded syllabus.
2. Use exactly the detected programming language: {language}.
3. The question must DIRECTLY test the selected topic.
4. Never create a "{language} adaptation" of a concept from
   another programming language.
5. Never replace a language-specific concept with a loosely
   related concept.
6. Do not repeat previous questions.
7. Keep the question appropriate for a college programming lab.
8. Generate exactly THREE deterministic hidden test cases.
9. Hidden tests must match the exact stated question.
10. Avoid file-based questions for automatic execution unless
    deterministic stdin/stdout testing is possible.

concept_key must be one of:

ARITHMETIC_OPERATORS
STRINGS
CONDITIONALS
LOOPS
ARRAYS
FUNCTIONS
OOP
POINTERS
STRUCTURES
FILES
DYNAMIC_MEMORY
OTHER

Return ONLY valid JSON:

{{
    "topic": "Exact syllabus topic",
    "concept_key": "POINTERS",
    "adaptation_reason": "Why this question was selected",
    "problem": "Programming problem in the detected language",
    "tests": [
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }},
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }},
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }}
    ]
}}
""",
        expected_output=(
            "One language-correct adaptive programming question"
        ),
        agent=adaptive_agent
    )


    crew = Crew(
        agents=[adaptive_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )


    result = crew.kickoff()

    return clean_json_output(
        result.raw
    )


@csrf_exempt
def adaptive_next_question(request):

    if request.method != "POST":

        return JsonResponse(
            {"error": "POST required"},
            status=405
        )


    try:

        data = json.loads(
            request.body or "{}"
        )

        student_id = data.get(
            "student_id"
        )


        state = load_state()


        if not state.get(
            "syllabus_text"
        ):

            return JsonResponse(
                {"error": "Upload syllabus first."},
                status=400
            )


        language = state.get(
            "language",
            "Python"
        )


        history = state.get(
            "history",
            []
        )


        weak_concept = get_weakest_concept(
            student_id
        )


        # ==================================================
        # EXISTING QUESTIONS IN SYLLABUS
        # ==================================================

        if state.get(
            "mode"
        ) == "existing_questions":

            questions = state.get(
                "existing_questions",
                []
            )

            index = state.get(
                "question_index",
                0
            )


            if index >= len(questions):

                return JsonResponse({

                    "finished": True,

                    "message":
                        "All syllabus questions have been completed."

                })


            problem = questions[
                index
            ]


            generated = generate_tests_for_question(
                problem,
                language
            )


            question = {

                "id":
                    str(uuid.uuid4()),

                "source":
                    "syllabus",

                "language":
                    language,

                "topic":
                    generated.get(
                        "concept_key",
                        "Programming"
                    ),

                "concept_key":
                    generated.get(
                        "concept_key",
                        "OTHER"
                    ),

                "adaptation_reason":
                    "This is an original question from the uploaded syllabus.",

                "problem":
                    problem,

                "tests":
                    generated.get(
                        "tests",
                        []
                    )
            }


            state[
                "question_index"
            ] = index + 1


        # ==================================================
        # TOPICS ONLY
        # ==================================================

        else:

            generated = generate_adaptive_question(

                state.get(
                    "topics",
                    []
                ),

                history,

                language,

                weak_concept
            )


            question = {

                "id":
                    str(uuid.uuid4()),

                "source":
                    (
                        "adaptive"
                        if weak_concept
                        else "generated"
                    ),

                "language":
                    language,

                "topic":
                    generated.get(
                        "topic",
                        "Programming"
                    ),

                "concept_key":
                    generated.get(
                        "concept_key",
                        "OTHER"
                    ),

                "adaptation_reason":
                    generated.get(
                        "adaptation_reason",
                        "Selected from the uploaded syllabus."
                    ),

                "problem":
                    generated.get(
                        "problem",
                        ""
                    ),

                "tests":
                    generated.get(
                        "tests",
                        []
                    )
            }


        if len(
            question["tests"]
        ) != 3:

            raise ValueError(
                "Exactly 3 hidden tests were not generated."
            )


        state[
            "current_question"
        ] = question


        history.append({

            "id":
                question["id"],

            "source":
                question["source"],

            "language":
                question["language"],

            "topic":
                question["topic"],

            "concept_key":
                question["concept_key"],

            "problem":
                question["problem"]
        })


        state[
            "history"
        ] = history


        save_state(
            state
        )


        execution_supported = (
            language
            in ["Python", "Java", "C"]
        )


        return JsonResponse({

            "finished":
                False,

            "id":
                question["id"],

            "source":
                question["source"],

            "language":
                language,

            "execution_supported":
                execution_supported,

            "topic":
                question["topic"],

            "concept_key":
                question["concept_key"],

            "problem":
                question["problem"],

            "question_number":
                len(history),

            "weak_concept":
                weak_concept,

            "adaptation_reason":
                question["adaptation_reason"]
        })


    except Exception as error:

        print(
            "ADAPTIVE NEXT ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )