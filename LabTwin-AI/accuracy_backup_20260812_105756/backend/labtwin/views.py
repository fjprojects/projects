import json
import os
import subprocess
import sys
import tempfile
import uuid
import shutil
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from pypdf import PdfReader

from crewai import Agent, Task, Crew, Process, LLM

import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda message: message


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = PROJECT_ROOT / "syllabus_state.json"

load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.1
)


syllabus_agent = Agent(
    role="Programming Lab Syllabus Analyzer",
    goal="Detect programming language, topics and existing lab questions from a syllabus.",
    backstory="You are an experienced university programming lab instructor.",
    llm=llm,
    verbose=False
)

question_agent = Agent(
    role="Programming Lab Question Generator",
    goal="Generate programming questions that directly test the exact syllabus topic in the correct programming language.",
    backstory="You never translate language-specific concepts into unrelated concepts from another language.",
    llm=llm,
    verbose=False
)

analyzer_agent = Agent(
    role="Programming Misconception Analyzer",
    goal="Identify the main programming misconception responsible for failed tests.",
    backstory="You diagnose only mistakes relevant to the stated problem.",
    llm=llm,
    verbose=False
)

tutor_agent = Agent(
    role="Adaptive Programming Tutor",
    goal="Help students correct misconceptions through hints, practice and viva.",
    backstory="You provide personalized guidance without immediately revealing full answers.",
    llm=llm,
    verbose=False
)

evaluator_agent = Agent(
    role="Programming Understanding Evaluator",
    goal="Evaluate corrected code and conceptual understanding.",
    backstory="You combine real code execution results with the viva answer.",
    llm=llm,
    verbose=False
)


def clean_json_output(output):
    if output is None:
        raise ValueError("AI returned an empty response.")

    text = str(output).strip()

    if not text:
        raise ValueError("AI returned an empty response.")

    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    object_start = text.find("{")
    object_end = text.rfind("}")

    if object_start != -1 and object_end > object_start:
        candidate = text[object_start:object_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    print("INVALID AI JSON RESPONSE:", repr(text[:1000]))
    raise ValueError("AI returned an invalid response. Please try again.")


def default_state():
    return {
        "student_id": None,
        "filename": "",
        "syllabus_text": "",
        "language": "Python",
        "mode": "",
        "topics": [],
        "existing_questions": [],
        "question_index": 0,
        "history": [],
        "current_question": None
    }


def load_state():
    if not STATE_FILE.exists():
        return default_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default_state()


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, ensure_ascii=False)


def extract_file_text(uploaded_file):
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages)

    if filename.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    raise ValueError("Only PDF and TXT files are supported.")


def get_current_question(question_id=None):
    state = load_state()
    question = state.get("current_question")

    if not question:
        return None

    if question_id and question.get("id") != question_id:
        return None

    return question


# ============================================================
# LANGUAGE DETECTION
# ============================================================

def analyze_syllabus_text(text):
    task = Task(
        description=f"""
Analyze this programming lab syllabus:

{text[:15000]}

Detect:

1. Main programming language.
2. Programming topics.
3. Whether actual lab questions already exist.

LANGUAGE RULES:

Return only one of:

Python
Java
C

Examples:

Pointers, function pointers, malloc, structures, unions
normally indicate C.

Classes, inheritance, JVM, interfaces, packages
normally indicate Java.

Python syntax, tuples, dictionaries, lists, indentation
normally indicate Python.

IMPORTANT:

Do not translate a language-specific concept into another language.

For example:

"Pointer to Function" is a C concept.
Do NOT convert it into Python built-in functions.

If actual programming questions exist:
mode = "existing_questions"

Otherwise:
mode = "topics"

Return ONLY valid JSON:

{{
    "language": "C",
    "mode": "topics",
    "topics": [
        "Pointers",
        "Pointer to Function"
    ],
    "existing_questions": []
}}
""",
        expected_output="Valid syllabus JSON",
        agent=syllabus_agent
    )

    crew = Crew(
        agents=[syllabus_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )

    last_error = None

    for attempt in range(3):
        try:
            result = crew.kickoff()
            raw = getattr(result, "raw", result)

            print(
                f"SYLLABUS AI RESPONSE attempt {attempt + 1}:",
                repr(str(raw)[:500])
            )

            return clean_json_output(raw)

        except Exception as error:
            last_error = error
            print(
                f"SYLLABUS ANALYSIS attempt {attempt + 1} failed:",
                error
            )

    raise ValueError(
        f"Syllabus AI analysis failed after 3 attempts: {last_error}"
    )


# ============================================================
# CODE RUNNERS
# ============================================================

def run_python_code(code, test_input):
    path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8"
        ) as file:
            file.write(code)
            path = file.name

        result = subprocess.run(
            [sys.executable, path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def run_java_code(code, test_input):
    temp_dir = tempfile.mkdtemp()

    try:
        source_path = os.path.join(
            temp_dir,
            "Main.java"
        )

        with open(
            source_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(code)

        compile_result = subprocess.run(
            ["javac", source_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr.strip()
            }

        result = subprocess.run(
            [
                "java",
                "-cp",
                temp_dir,
                "Main"
            ],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )



def run_c_code(code, test_input):
    temp_dir = tempfile.mkdtemp()

    try:
        source_path = os.path.join(
            temp_dir,
            "main.c"
        )

        executable_path = os.path.join(
            temp_dir,
            "program.exe"
        )

        with open(
            source_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(code)

        # -----------------------------
        # COMPILE C CODE
        # -----------------------------

        compile_result = subprocess.run(
            [
                "gcc",
                source_path,
                "-o",
                executable_path,
                "-std=c11"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr.strip()
            }

        # -----------------------------
        # EXECUTE COMPILED PROGRAM
        # -----------------------------

        result = subprocess.run(
            [executable_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


def run_tests(student_code, tests, language):

    results = []
    passed_count = 0

    for index, test in enumerate(
        tests,
        start=1
    ):

        test_input = str(
            test.get("input", "")
        )

        if language == "Java":
            execution = run_java_code(
                student_code,
                test_input
            )

        elif language == "Python":
            execution = run_python_code(
                student_code,
                test_input
            )

        elif language == "C":
            execution = run_c_code(
                student_code,
                test_input
            )

        else:
            raise ValueError(
                f"Unsupported programming language: {language}"
            )

        expected = str(
            test.get("expected", "")
        ).strip()

        actual = execution[
            "stdout"
        ].strip()

        passed = (
            execution["success"]
            and actual == expected
        )

        if passed:
            passed_count += 1

        results.append({
            "test": index,
            "input": test_input,
            "expected": expected,
            "actual": (
                actual
                if execution["success"]
                else execution["stderr"]
            ),
            "passed": passed
        })

    if not tests:
        return 0, []

    score = round(
        passed_count / len(tests) * 100
    )

    return score, results


# ============================================================
# QUESTION GENERATION
# ============================================================

def generate_tests_for_question(
    problem,
    language
):

    java_rule = ""

    if language == "Java":
        java_rule = """
The submitted Java program must use:

public class Main

so it can be compiled automatically.
"""

    task = Task(
        description=f"""
Programming language:

{language}

EXISTING SYLLABUS QUESTION:

{problem}

Create exactly THREE hidden stdin/stdout tests.

IMPORTANT:

The tests must match the exact question.

Do NOT change the original concept.

{java_rule}

Return ONLY JSON:

{{
    "concept_key": "FUNCTIONS",
    "tests": [
        {{
            "input": "input",
            "expected": "exact output"
        }},
        {{
            "input": "input",
            "expected": "exact output"
        }},
        {{
            "input": "input",
            "expected": "exact output"
        }}
    ]
}}

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
OTHER
""",
        expected_output="Exactly three hidden tests",
        agent=question_agent
    )

    crew = Crew(
        agents=[question_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )

    return clean_json_output(
        crew.kickoff().raw
    )


def generate_question_from_topics(
    topics,
    history,
    language
):

    previous = [
        item.get("problem", "")
        for item in history[-10:]
    ]

    execution_note = ""

    if language == "Java":
        execution_note = """
Require the student to write:

public class Main

with a public static void main(String[] args).
"""

    if language == "C":
        execution_note = """
Generate a genuine C programming problem.

C-specific topics such as pointers,
function pointers, structures and unions
must remain genuine C concepts.
"""

    task = Task(
        description=f"""
Generate ONE programming lab question.

PROGRAMMING LANGUAGE:

{language}

ALLOWED SYLLABUS TOPICS:

{json.dumps(topics, indent=2)}

PREVIOUS QUESTIONS:

{json.dumps(previous, indent=2)}

STRICT RULES:

1. Use ONLY the uploaded syllabus topics.
2. Use the detected programming language: {language}.
3. The question must DIRECTLY test the selected topic.
4. Never replace a language-specific concept with a loose equivalent.
5. Do not repeat previous questions.
6. Keep input/output deterministic.
7. Generate exactly THREE hidden tests.
8. No files, GUI, internet or external packages.

{execution_note}

For example:

If topic = Pointer to Function
and language = C,

generate a genuine C function-pointer problem,
NOT a Python function selection problem.

Return ONLY JSON:

{{
    "topic": "Pointer to Function",
    "concept_key": "POINTERS",
    "problem": "Programming question",
    "tests": [
        {{
            "input": "input",
            "expected": "output"
        }},
        {{
            "input": "input",
            "expected": "output"
        }},
        {{
            "input": "input",
            "expected": "output"
        }}
    ]
}}
""",
        expected_output="One language-correct programming question",
        agent=question_agent
    )

    crew = Crew(
        agents=[question_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )

    return clean_json_output(
        crew.kickoff().raw
    )


# ============================================================
# UPLOAD
# ============================================================

@csrf_exempt
def upload_syllabus(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        syllabus_file = request.FILES.get(
            "syllabus"
        )

        if not syllabus_file:
            return JsonResponse(
                {"error": "Select a syllabus file."},
                status=400
            )

        text = extract_file_text(
            syllabus_file
        )

        analysis = analyze_syllabus_text(
            text
        )

        state = default_state()

        state["student_id"] = request.POST.get(
            "student_id"
        )

        state["filename"] = syllabus_file.name

        state["syllabus_text"] = text

        state["language"] = analysis.get(
            "language",
            "Python"
        )

        state["mode"] = analysis.get(
            "mode",
            "topics"
        )

        state["topics"] = analysis.get(
            "topics",
            []
        )

        state["existing_questions"] = analysis.get(
            "existing_questions",
            []
        )

        save_state(state)

        execution_supported = (
            state["language"]
            in ["Python", "Java", "C"]
        )

        return JsonResponse({
            "success": True,
            "filename": state["filename"],
            "language": state["language"],
            "mode": state["mode"],
            "topics": state["topics"],
            "existing_question_count": len(
                state["existing_questions"]
            ),
            "execution_supported": execution_supported
        })

    except Exception as error:
        print(
            "UPLOAD ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


# ============================================================
# NEXT QUESTION
# ============================================================

@csrf_exempt
def next_question(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
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
                    "message": "All syllabus questions completed."
                })

            problem = questions[index]

            generated = generate_tests_for_question(
                problem,
                language
            )

            question = {
                "id": str(uuid.uuid4()),
                "source": "syllabus",
                "language": language,
                "topic": generated.get(
                    "concept_key",
                    "Programming"
                ),
                "concept_key": generated.get(
                    "concept_key",
                    "OTHER"
                ),
                "problem": problem,
                "tests": generated.get(
                    "tests",
                    []
                )
            }

            state["question_index"] = (
                index + 1
            )

        else:

            generated = generate_question_from_topics(
                state.get("topics", []),
                history,
                language
            )

            question = {
                "id": str(uuid.uuid4()),
                "source": "generated",
                "language": language,
                "topic": generated.get(
                    "topic",
                    "Programming"
                ),
                "concept_key": generated.get(
                    "concept_key",
                    "OTHER"
                ),
                "problem": generated.get(
                    "problem",
                    ""
                ),
                "tests": generated.get(
                    "tests",
                    []
                )
            }

        state["current_question"] = question

        history.append({
            "id": question["id"],
            "source": question["source"],
            "language": language,
            "topic": question["topic"],
            "concept_key": question["concept_key"],
            "problem": question["problem"]
        })

        state["history"] = history

        save_state(state)

        return JsonResponse({
            "finished": False,
            "id": question["id"],
            "source": question["source"],
            "language": language,
            "execution_supported": (
                language in [
                    "Python",
                    "Java",
                    "C"
                ]
            ),
            "topic": question["topic"],
            "concept_key": question["concept_key"],
            "problem": question["problem"],
            "question_number": len(history)
        })

    except Exception as error:
        print(
            "NEXT QUESTION ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


# ============================================================
# ANALYZE
# ============================================================

@csrf_exempt
def analyze_code(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body
        )

        code = data.get(
            "code",
            ""
        ).strip()

        question = get_current_question(
            data.get("question_id")
        )

        if not question:
            return JsonResponse(
                {"error": "Question not found."},
                status=400
            )

        language = question.get(
            "language",
            "Python"
        )

        score, results = run_tests(
            code,
            question["tests"],
            language
        )

        if score == 100:

            return JsonResponse({
                "test_score": 100,
                "test_results": results,
                "diagnosis": {
                    "has_misconception": False,
                    "concept_key": question[
                        "concept_key"
                    ],
                    "misconception": None,
                    "explanation": "The solution correctly solves the problem and passes all hidden tests.",
                    "hint": "No correction is needed."
                }
            })

        task = Task(
            description=f"""
LANGUAGE:
{language}

QUESTION:
{question["problem"]}

CONCEPT:
{question["concept_key"]}

STUDENT CODE:
{code}

REAL TEST RESULTS:
{json.dumps(results, indent=2)}

Identify the SINGLE MAIN misconception.

Return ONLY JSON:

{{
    "has_misconception": true,
    "concept_key": "{question["concept_key"]}",
    "misconception": "Main mistake",
    "explanation": "Why the program failed",
    "hint": "Helpful clue"
}}
""",
            expected_output="Valid JSON",
            agent=analyzer_agent
        )

        crew = Crew(
            agents=[analyzer_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        diagnosis = clean_json_output(
            crew.kickoff().raw
        )

        diagnosis[
            "has_misconception"
        ] = True

        return JsonResponse({
            "test_score": score,
            "test_results": results,
            "diagnosis": diagnosis
        })

    except Exception as error:
        print(
            "ANALYZE ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


# ============================================================
# TUTOR
# ============================================================

@csrf_exempt
def tutor_help(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        concept = data.get(
            "concept_key",
            "OTHER"
        )

        topic = data.get(
            "topic",
            concept
        )

        misconception = data.get(
            "misconception",
            ""
        )

        passed_code = bool(
            data.get(
                "passed_code",
                False
            )
        )

        if passed_code:
            tutor_mode = """
The student's code already passes all hidden tests.

Do NOT give correction help.

Generate:
1. A short conceptual viva question for the exact topic.
2. Three concise expected concepts that a strong answer should cover.
3. Keep hint and practice_problem empty strings.

This is a concept-verification step, not remediation.
"""
        else:
            tutor_mode = """
The student's code failed.

Generate:
1. One progressive conceptual hint.
2. One short targeted practice problem.
3. One viva question that checks the exact misconception.
4. Three concise expected concepts that a strong viva answer should cover.

Do not reveal the complete solution.
"""

        task = Task(
            description=f"""
PROGRAMMING TOPIC:
{topic}

BROAD CONCEPT:
{concept}

MISCONCEPTION:
{misconception}

{tutor_mode}

Return ONLY JSON:

{{
    "hint": "Progressive hint or empty string",
    "practice_problem": "Short related practice problem or empty string",
    "viva_question": "One conceptual viva question",
    "expected_concepts": [
        "Expected concept 1",
        "Expected concept 2",
        "Expected concept 3"
    ]
}}
""",
            expected_output="Valid JSON",
            agent=tutor_agent
        )

        crew = Crew(
            agents=[tutor_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        result = clean_json_output(
            crew.kickoff().raw
        )

        expected = result.get(
            "expected_concepts",
            []
        )

        if not isinstance(
            expected,
            list
        ):
            expected = []

        result[
            "expected_concepts"
        ] = [
            str(item).strip()
            for item in expected
            if str(item).strip()
        ][:3]

        return JsonResponse(
            result
        )

    except Exception as error:
        return JsonResponse(
            {"error": str(error)},
            status=500
        )


# ============================================================
# EVALUATE
# ============================================================

@csrf_exempt
def evaluate_code(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        question = get_current_question(
            data.get("question_id")
        )

        if not question:
            return JsonResponse(
                {"error": "Question not found."},
                status=400
            )

        language = question.get(
            "language",
            "Python"
        )

        corrected_code = data.get(
            "code",
            ""
        ).strip()

        viva_answer = data.get(
            "viva_answer",
            ""
        ).strip()

        misconception = data.get(
            "misconception",
            ""
        )

        initial_score = float(
            data.get(
                "initial_score",
                0
            )
            or 0
        )

        hint_level = int(
            data.get(
                "hint_level",
                0
            )
            or 0
        )

        hint_level = max(
            0,
            min(
                3,
                hint_level
            )
        )

        verification = bool(
            data.get(
                "verification",
                False
            )
        )

        expected_concepts = data.get(
            "expected_concepts",
            []
        )

        if not isinstance(
            expected_concepts,
            list
        ):
            expected_concepts = []

        expected_concepts = [
            str(item).strip()
            for item in expected_concepts
            if str(item).strip()
        ][:5]

        if not expected_concepts:
            expected_concepts = [
                f"Correct conceptual understanding of {question.get('topic', question.get('concept_key', 'the topic'))}"
            ]

        retest_score, retest_results = run_tests(
            corrected_code,
            question["tests"],
            language
        )

        task = Task(
            description=f"""
You are grading ONLY conceptual understanding in a programming viva.

PROGRAMMING LANGUAGE:
{language}

TOPIC:
{question.get("topic", "")}

QUESTION:
{question["problem"]}

PREVIOUS MISCONCEPTION:
{misconception}

VIVA ANSWER:
{viva_answer}

EXPECTED CONCEPTS:
{json.dumps(expected_concepts, indent=2)}

For every expected concept, decide whether the student's answer
clearly demonstrates it.

IMPORTANT:
- EXPECTED CONCEPTS are zero-indexed in the order shown.
- "covered_indices" must contain only integer indices of concepts
  clearly demonstrated by the student's answer.
- "missing_indices" must contain the remaining integer indices.
- If the answer states something conceptually false, put a short
  description in "contradictions".
- Do NOT assign the final numeric score or mastery status.

Return ONLY valid JSON:

{{
    "covered_indices": [],
    "missing_indices": [],
    "contradictions": [],
    "reason": "Short evidence-based feedback"
}}
""",
            expected_output="Valid JSON rubric evaluation",
            agent=evaluator_agent
        )

        crew = Crew(
            agents=[evaluator_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        rubric = clean_json_output(
            crew.kickoff().raw
        )

        covered_raw = rubric.get(
            "covered_indices",
            []
        )

        contradictions = rubric.get(
            "contradictions",
            []
        )

        if not isinstance(
            covered_raw,
            list
        ):
            covered_raw = []

        if not isinstance(
            contradictions,
            list
        ):
            contradictions = []

        covered_indices = []

        for item in covered_raw:
            try:
                index = int(item)
            except Exception:
                continue

            if (
                0 <= index < len(
                    expected_concepts
                )
                and index
                not in covered_indices
            ):
                covered_indices.append(
                    index
                )

        covered_indices.sort()

        covered = [
            expected_concepts[index]
            for index in covered_indices
        ]

        missing = [
            concept
            for index, concept
            in enumerate(
                expected_concepts
            )
            if index not in covered_indices
        ]

        if not viva_answer:
            understanding = 0

        else:
            understanding = round(
                len(covered)
                / max(
                    1,
                    len(expected_concepts)
                )
                * 100
            )

        # A direct conceptual contradiction is strong evidence that
        # the topic is not yet understood, even if some keywords
        # were present.
        if contradictions:
            understanding = min(
                understanding,
                35
            )

        if retest_score < 80:
            status = "Needs Coding Practice"

        elif understanding < 40:
            status = "Needs Practice"

        elif understanding < 70:
            status = "Needs Verification"

        elif verification:
            status = "Mastered"

        else:
            # Good correction / good first solution is strong evidence,
            # but LabTwin still requires a separate independent question.
            status = "Needs Verification"

        independence_score = max(
            10,
            100 - (
                30 * hint_level
            )
        )

        verification_score = (
            100
            if (
                verification
                and retest_score >= 80
                and understanding >= 70
            )
            else 0
        )

        topic_evidence_score = round(
            (0.35 * initial_score)
            + (0.25 * understanding)
            + (0.15 * retest_score)
            + (0.15 * verification_score)
            + (0.10 * independence_score),
            1
        )

        if not verification:
            topic_evidence_score = min(
                topic_evidence_score,
                79.0
            )

        evaluation = {
            "status":
                status,
            "score":
                understanding,
            "reason":
                rubric.get(
                    "reason",
                    ""
                ),
            "covered_concepts":
                covered,
            "missing_concepts":
                missing,
            "contradictions":
                [
                    str(item)
                    for item in contradictions
                ],
        }

        return JsonResponse({
            "retest_score":
                retest_score,
            "retest_results":
                retest_results,
            "evaluation":
                evaluation,
            "initial_score":
                initial_score,
            "hint_level":
                hint_level,
            "verification":
                verification,
            "topic_evidence_score":
                topic_evidence_score,
            # The frontend replaces this with the persisted dashboard
            # readiness after save_attempt completes.
            "lab_readiness":
                topic_evidence_score
        })

    except Exception as error:
        print(
            "EVALUATE ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )

