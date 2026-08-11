
# LabTwin AI

## Autonomous Programming Lab Coach

LabTwin AI is an agentic AI-powered programming lab coach designed to help students understand programming concepts instead of simply memorizing lab programs.

## Problem Statement

Students often memorize programming lab programs without understanding the underlying concepts. Traditional coding platforms mainly tell students whether their answer is correct or wrong, but they do not identify recurring conceptual weaknesses or adapt future questions based on those weaknesses.

## Solution

LabTwin AI creates a personalized programming lab learning experience.

A student can upload their actual lab syllabus, after which LabTwin AI detects the programming language, topics, and available lab questions.

The system then:

1. Selects or generates a question strictly from the uploaded syllabus.
2. Executes the student's code using hidden test cases.
3. Detects the underlying misconception when the code fails.
4. Provides progressive hints instead of immediately revealing the answer.
5. Generates a targeted practice problem and viva question.
6. Allows the student to correct the program.
7. Retests the corrected solution.
8. Stores the student's learning progress and weaknesses.
9. Generates future questions based on previous misconceptions.
10. Calculates the student's overall lab readiness.

## Key Features

- Syllabus-based question generation
- Automatic programming-language detection
- Python, Java and C code execution
- Hidden test-case evaluation
- Conceptual misconception detection
- Progressive AI hints
- Personalized practice problems
- AI-generated viva questions
- Corrected-code retesting
- Persistent student learning memory
- Adaptive next-question generation
- Lab readiness dashboard
- Multi-student learning profiles

## Agentic AI Workflow


Upload Syllabus
      |
      v
Syllabus Analyzer Agent
      |
      v
Question Generator
      |
      v
Student Code
      |
      v
Hidden Test Execution
      |
      +------ Correct ------> Mastery Update
      |
      v
Code Analyzer Agent
      |
      v
Misconception Detection
      |
      v
Adaptive Tutor Agent
      |
      +--> Progressive Hint
      +--> Practice Problem
      +--> Viva Question
      |
      v
Corrected Code
      |
      v
Evaluator Agent
      |
      v
Student Memory Update
      |
      v
Adaptive Next Question


## Tech Stack

### Frontend

* React
* Vite
* CSS
* Axios

### Backend

* Django
* Python

### Agentic AI

* CrewAI
* Groq LLM

### Database

* SQLite

### Code Execution

* Python Interpreter
* Java JDK / javac
* GCC for C

### Other Tools

* PyPDF
* Git
* GitHub

## Team Members

* Fancis
* Jomon JoJo
*Parvathy

