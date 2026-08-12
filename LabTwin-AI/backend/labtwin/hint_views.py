import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crewai import Agent, Task, Crew, Process

from .views import llm, clean_json_output


hint_agent = Agent(
    role="Progressive Hint Coach",
    goal=(
        "Give increasingly useful programming hints without "
        "revealing the complete solution."
    ),
    backstory=(
        "You are a programming lab instructor. "
        "Students should think independently. "
        "Hint level 1 is subtle, level 2 is more specific, "
        "and level 3 is strong guidance but must still avoid "
        "providing complete code."
    ),
    llm=llm,
    verbose=False
)


@csrf_exempt
def progressive_hint(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(request.body)

        problem = data.get("problem", "")
        concept = data.get("concept_key", "OTHER")
        misconception = data.get("misconception", "")
        level = int(data.get("level", 1))

        if level < 1:
            level = 1

        if level > 3:
            level = 3


        if level == 1:
            instruction = """
Give a SMALL conceptual clue.
Do not mention the exact line that needs changing.
Do not provide code.
"""

        elif level == 2:
            instruction = """
Give a MORE SPECIFIC clue.
Tell the student which concept or part of the logic
they should inspect.
You may give tiny syntax fragments, but not the solution.
"""

        else:
            instruction = """
Give STRONG guidance.
Explain the correction approach step by step,
but DO NOT provide the complete finished program.
"""


        task = Task(
            description=f"""
PROGRAMMING QUESTION:

{problem}

CONCEPT:

{concept}

DETECTED MISCONCEPTION:

{misconception}

CURRENT HINT LEVEL:

{level}

{instruction}

The hint must address the detected misconception and
the exact programming question.

Return ONLY valid JSON:

{{
    "level": {level},
    "hint": "Your progressive hint",
    "strength": "Low"
}}

Use strength:

Level 1 = Low
Level 2 = Medium
Level 3 = High
""",
            expected_output="Valid JSON progressive hint",
            agent=hint_agent
        )


        crew = Crew(
            agents=[hint_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        result = crew.kickoff()

        hint_data = clean_json_output(
            result.raw
        )

        hint_data["level"] = level

        return JsonResponse(
            hint_data
        )


    except Exception as error:

        print(
            "PROGRESSIVE HINT ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )
