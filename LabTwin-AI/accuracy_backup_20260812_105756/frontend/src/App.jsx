import { useEffect, useState } from "react";
import axios from "axios";
import "./App.css";

const API = "http://127.0.0.1:8000/api";


function App() {
  // RESTORE_ACTIVE_STUDENT_SESSION
  useEffect(() => {

    const savedStudent =
      sessionStorage.getItem("labtwin_student");

    if (savedStudent) {

      try {

        const parsedStudent =
          JSON.parse(savedStudent);

        setStudent(parsedStudent);

      } catch (error) {

        sessionStorage.removeItem(
          "labtwin_student"
        );

      }
    }

  }, []);


  const [studentName, setStudentName] =
    useState("");

  const [student, setStudent] =
    useState(null);


  const [file, setFile] =
    useState(null);

  const [syllabus, setSyllabus] =
    useState(null);


  const [question, setQuestion] =
    useState(null);

  const [code, setCode] =
    useState("");


  const [analysis, setAnalysis] =
    useState(null);

  const [tutor, setTutor] =
    useState(null);


  const [correctedCode, setCorrectedCode] =
    useState("");

  const [vivaAnswer, setVivaAnswer] =
    useState("");


  const [evaluation, setEvaluation] =
    useState(null);

  const [progress, setProgress] =
    useState(null);


  const [loading, setLoading] =
    useState(false);


  // ======================================================
  // RESTORE STUDENT
  // ======================================================


  // ======================================================
  // START STUDENT
  // ======================================================

  const startStudent = async () => {

    if (!studentName.trim()) {

      alert(
        "Enter student name."
      );

      return;
    }


    try {

      setLoading(true);


      const response =
        await axios.post(

          `${API}/start-student/`,

          {
            name:
              studentName
          }

        );


      setStudent(
        response.data
      );

      // A student must never inherit another student's
      // syllabus, question, code, analysis or evaluation.
      setFile(null);
      setSyllabus(null);
      setQuestion(null);
      setCode("");
      setAnalysis(null);
      setTutor(null);
      setCorrectedCode("");
      setVivaAnswer("");
      setEvaluation(null);
      setProgress(null);


      sessionStorage.setItem(

        "labtwin_student",

        JSON.stringify(
          response.data
        )

      );


      await loadProgress(
        response.data.student_id
      );


    } catch (error) {

      console.error(
        error
      );

      alert(
        "Could not start student session."
      );

    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // LOAD DASHBOARD
  // ======================================================

  const loadProgress = async (
    studentId = null
  ) => {

    const id =
      studentId ||
      student?.student_id;


    if (!id) {
      return;
    }


    try {

      const response =
        await axios.get(

          `${API}/progress/?student_id=${id}`

        );


      setProgress(
        response.data
      );

      return response.data;


    } catch (error) {

      console.error(
        error
      );

    }
  };


  // ======================================================
  // RESET QUESTION
  // ======================================================

  const resetQuestionWork = () => {

    setCode("");

    setAnalysis(null);

    setTutor(null);

    setCorrectedCode("");

    setVivaAnswer("");

    setEvaluation(null);

  };


  // ======================================================
  // UPLOAD SYLLABUS
  // ======================================================

  const uploadSyllabus = async () => {

    if (!file) {

      alert(
        "Choose syllabus PDF or TXT."
      );

      return;
    }


    try {

      setLoading(true);


      const formData =
        new FormData();


      formData.append(
        "syllabus",
        file
      );

      formData.append(
        "student_id",
        student?.student_id || ""
      );


      const response =
        await axios.post(

          `${API}/upload-syllabus/`,

          formData

        );


      setSyllabus(
        response.data
      );


      await nextQuestion();


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Syllabus upload failed."

      );


    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // NEXT QUESTION
  // ======================================================

  const nextQuestion = async () => {

    try {

      setLoading(true);

      resetQuestionWork();


      const response =
        await axios.post(

          `${API}/adaptive-next-question/`,

          { student_id: student?.student_id }

        );


      if (
        response.data.finished
      ) {

        alert(
          response.data.message
        );

        return;
      }


      setQuestion(
        response.data
      );


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Could not generate question."

      );


    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // SAVE MEMORY
  // ======================================================

  const saveAttempt = async ({
    initialScore,
    finalScore = null,
    vivaScore = null,
    misconception = "",
    status,
    topic = question?.topic || "General",
    hintLevel = 0,
    verification = question?.is_verification || false
  }) => {

    if (
      !student ||
      !question
    ) {

      return;
    }


    try {

      await axios.post(

        `${API}/save-attempt/`,

        {

          student_id:
            student.student_id,

          question:
            question.problem,

          concept_key:
            question.concept_key,

          topic:
            topic,

          hint_level:
            hintLevel,

          verification:
            verification,

          initial_score:
            initialScore,

          final_score:
            finalScore,

          viva_score:
            vivaScore,

          misconception:
            misconception,

          status:
            status

        }

      );


      const latestProgress =
        await loadProgress(
          student.student_id
        );

      return latestProgress;


    } catch (error) {

      console.error(
        "Memory save failed:",
        error
      );

    }
  };


  // ======================================================
  // ANALYZE
  // ======================================================

  const analyzeCode = async () => {

    if (!code.trim()) {

      alert(
        "Enter your code."
      );

      return;
    }


    try {

      setLoading(true);

      setAnalysis(null);

      setTutor(null);

      setEvaluation(null);


      const response =
        await axios.post(

          `${API}/analyze/`,

          {

            question_id:
              question.id,

            code:
              code

          }

        );


      setAnalysis(
        response.data
      );


      const diagnosis =
        response.data.diagnosis;


      // ----------------------------------
      // CORRECT ON FIRST TRY
      // ----------------------------------

      if (
        response.data.test_score === 100
      ) {

        const tutorResponse =
          await axios.post(

            `${API}/tutor/`,

            {
              concept_key:
                diagnosis.concept_key,

              topic:
                question.topic,

              misconception:
                "No coding error. Verify conceptual understanding of this exact topic.",

              passed_code:
                true
            }

          );


        setTutor({
          ...tutorResponse.data,
          concept_check: true
        });

        setCorrectedCode(
          code
        );

        return;
      }


      // ----------------------------------
      // WRONG ? TUTOR
      // ----------------------------------

      const tutorResponse =
        await axios.post(

          `${API}/tutor/`,

          {

            concept_key:
              diagnosis.concept_key,

            topic:
              question.topic,

            misconception:
              diagnosis.misconception,

            passed_code:
              false

          }

        );


      setTutor(
        tutorResponse.data
      );


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Analysis failed."

      );


    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // EVALUATE CORRECTION
  // ======================================================

  const evaluateCode = async () => {

    try {

      setLoading(true);


      const hintLevel =
        analysis?.test_score === 100
          ? 0
          : 1;


      const response =
        await axios.post(

          `${API}/evaluate/`,

          {

            question_id:
              question.id,

            concept_key:
              analysis.diagnosis
                .concept_key,

            misconception:
              analysis.diagnosis
                .misconception || "",

            code:
              correctedCode,

            viva_answer:
              vivaAnswer,

            initial_score:
              analysis.test_score,

            hint_level:
              hintLevel,

            verification:
              question?.is_verification || false,

            expected_concepts:
              tutor?.expected_concepts || []

          }

        );


      const latestProgress =
        await saveAttempt({

          initialScore:
            analysis.test_score,

          finalScore:
            response.data.retest_score,

          vivaScore:
            response.data.evaluation.score,

          misconception:
            analysis.diagnosis
              .misconception || "",

          status:
            response.data.evaluation.status,

          topic:
            question.topic,

          hintLevel:
            hintLevel,

          verification:
            question?.is_verification || false

        });


      const topicProgress =
        latestProgress?.topics?.find(
          (item) =>
            item.topic === question.topic
        );


      setEvaluation({

        ...response.data,

        lab_readiness:
          latestProgress?.lab_readiness ??
          response.data.lab_readiness,

        topic_mastery:
          topicProgress?.mastery_score ??
          response.data.topic_evidence_score,

        evaluation: {
          ...response.data.evaluation,

          status:
            topicProgress?.status ??
            response.data.evaluation.status
        }

      });


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Evaluation failed."

      );


    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // CHANGE STUDENT
  // ======================================================

  const changeStudent = () => {

  sessionStorage.removeItem("labtwin_student");

  setStudent(null);
  setStudentName("");
  setProgress(null);
  setSyllabus(null);
  setQuestion(null);
  setFile(null);
  setCode("");
  setAnalysis(null);
  setTutor(null);
  setCorrectedCode("");
  setVivaAnswer("");
  setEvaluation(null);
};


  const mastered = false;


  // ======================================================
  // UI
  // ======================================================

  return (

    <div className="app">


      <div className="header">

        <h1>
          LabTwin AI
        </h1>

        <p>
          Autonomous Programming Lab Coach
        </p>

      </div>


      {/* ================================================= */}
      {/* STUDENT */}
      {/* ================================================= */}

      {!student ? (

        <div className="card">

          <h2>
            Start Learning Session
          </h2>


          <p>
            Enter your name to create your
            personalized LabTwin profile.
          </p>


          <input

            type="text"

            value={
              studentName
            }

            onChange={(e) =>
              setStudentName(
                e.target.value
              )
            }

            placeholder={
              "Student name"
            }

          />


          <br />
          <br />


          <button
            onClick={
              startStudent
            }
            disabled={
              loading
            }
          >

            Start Session

          </button>

        </div>

      ) : (

        <div className="card">

          <h2>
            Welcome, {
              student.name
            }
          </h2>


          <button
            onClick={
              changeStudent
            }
          >
            Change Student
          </button>

        </div>

      )}


      {/* ================================================= */}
      {/* DASHBOARD */}
      {/* ================================================= */}

      {student && progress && (

        <div className="card report">


          <h2>
            Learning Dashboard
          </h2>


          <div className="reportGrid">


            <div>

              <span>
                Questions Attempted
              </span>

              <strong>
                {
                  progress.questions_attempted
                }
              </strong>

            </div>


            <div>

              <span>
                Topics Mastered
              </span>

              <strong>
                {
                  progress.mastered
                }
              </strong>

            </div>


            <div>

              <span>
                Syllabus Coverage
              </span>

              <strong>
                {
                  progress.syllabus_coverage
                }%
              </strong>

            </div>


            <div>

              <span>
                Overall Lab Readiness
              </span>

              <strong>
                {
                  progress.lab_readiness
                }%
              </strong>

            </div>


          </div>


          <p
            style={{
              marginTop: "18px"
            }}
          >
            Tested-topic mastery average:{" "}
            <strong>
              {
                progress.topic_mastery_average
              }%
            </strong>
          </p>


          {progress.weakest_topic && (

            <div
              className="adaptiveBox"
              style={{
                marginTop: "20px"
              }}
            >

              <h3>
                Current Learning Priority
              </h3>


              <p>

                <strong>
                  {
                    progress
                      .weakest_topic
                      .topic
                  }
                </strong>

              </p>


              <p>
                Topic mastery:{" "}
                {
                  progress
                    .weakest_topic
                    .mastery_score
                }%
              </p>


              <p>
                Status:{" "}
                <strong>
                  {
                    progress
                      .weakest_topic
                      .status
                  }
                </strong>
              </p>


              {
                progress
                  .weakest_topic
                  .verification_required
                && (

                  <p>
                    Next action: solve another independent question on this exact topic.
                  </p>

                )
              }


              {
                progress
                  .weakest_topic
                  .last_misconception
                && (

                  <p>
                    Recurring weakness:{" "}
                    {
                      progress
                        .weakest_topic
                        .last_misconception
                    }
                  </p>

                )
              }


              <p>
                Hint dependency:{" "}
                {
                  progress
                    .weakest_topic
                    .average_hint_level
                }
              </p>

            </div>

          )}


        </div>

      )}


      {/* ================================================= */}
      {/* SYLLABUS */}
      {/* ================================================= */}

      {student && (

        <div className="card">


          <h2>
            Upload Lab Syllabus
          </h2>


          <p>

            LabTwin will use existing
            questions if present.

            Otherwise it will generate
            questions only from syllabus
            topics.

          </p>


          <input

            type="file"

            accept=".pdf,.txt"

            onChange={(e) =>
              setFile(
                e.target.files[0]
              )
            }

          />


          <br />
          <br />


          <button
            onClick={
              uploadSyllabus
            }
            disabled={
              loading ||
              !file
            }
          >

            {
              loading
                ? "Analyzing..."
                : "Upload & Analyze Syllabus"
            }

          </button>


          {syllabus && (

            <div
              style={{
                marginTop: "20px"
              }}
            >

              <p>
                {
                  syllabus.filename
                }
              </p>


              <p>

                <strong>
                  Mode:
                </strong>{" "}

                {
                  syllabus.mode ===
                  "existing_questions"

                    ? "Existing questions detected"

                    : "Questions generated from syllabus topics"
                }

              </p>


              <p>

                <strong>
                  Topics:
                </strong>{" "}

                {
                  syllabus.topics?.join(
                    ", "
                  )
                }

              </p>


              {
                syllabus.mode ===
                "existing_questions"
                && (

                  <p>

                    Questions found:{" "}

                    {
                      syllabus.existing_question_count
                    }

                  </p>

                )
              }

            </div>

          )}


        </div>

      )}


      {/* ================================================= */}
      {/* QUESTION */}
      {/* ================================================= */}

      {question && (

        <div className="card">


          <div
            style={{
              display: "flex",
              justifyContent:
                "space-between",
              alignItems: "center",
              gap: "20px"
            }}
          >


            <div>

              <h2>

                Question {
                  question.question_number
                }

              </h2>


              <p>

                {
                  question.is_verification

                    ? "Independent verification of your current weak topic"

                    : question.source ===
                      "syllabus"

                      ? "From uploaded syllabus"

                      : "Generated from syllabus topic"
                }

              </p>

            </div>


            <button
              onClick={
                nextQuestion
              }
              disabled={
                loading
              }
            >

              Next Question

            </button>

          </div>


          <h3>
            Programming Language
          </h3>

          <p>
            {question.language}
          </p>

          {question.language === "C" && (

            <div className="adaptiveBox">

              <strong>
                C question detected
              </strong>

              <p>
                LabTwin detected a C programming concept.
                Your C code will be compiled using GCC and tested automatically.
              </p>

            </div>

          )}

          <h3>
            Topic
          </h3>


          <p>
            {
              question.topic
            }
          </p>


          <h3>
            Programming Problem
          </h3>


          <p>
            {
              question.problem
            }
          </p>


          <h3>
            Your Code
          </h3>


          <textarea

            value={
              code
            }

            onChange={(e) =>
              setCode(
                e.target.value
              )
            }

            placeholder={
              `Write your ${question?.language || "programming"} code here...`
            }

          />


          <button
            onClick={
              analyzeCode
            }
            disabled={
              loading ||
              !code.trim() ||
              question?.execution_supported === false
            }
          >

            {
              loading
                ? "Working..."
                : "Analyze Code"
            }

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* ANALYSIS */}
      {/* ================================================= */}

      {analysis && (

        <div className="card">


          <h2>
            Code Analysis
          </h2>


          <h3>

            Initial Test Score:{" "}

            {
              analysis.test_score
            }%

          </h3>


          <h3>
            Hidden Test Cases
          </h3>


          {
            analysis
              .test_results
              .map(
                (test) => (

                  <p
                    key={
                      test.test
                    }
                  >

                    Test {
                      test.test
                    }:{" "}

                    {
                      test.passed
                        ? "PASS"
                        : "FAIL"
                    }

                  </p>

                )
              )
          }


          <h3>
            Detected Concept
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .concept_key
            }

          </p>


          <h3>
            Misconception
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .misconception
              ||
              "No misconception detected"
            }

          </p>


          <h3>
            Explanation
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .explanation
            }

          </p>


          <h3>
            Hint
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .hint
            }

          </p>


        </div>

      )}


      {/* ================================================= */}
      {/* MASTERED */}
      {/* ================================================= */}

      {mastered && (

        <div className="card report">


          <h2>
            Current Problem Mastered
          </h2>


          <p>
            All hidden tests passed.
          </p>


          <div className="reportGrid">


            <div>

              <span>
                Test Score
              </span>

              <strong>
                100%
              </strong>

            </div>


            <div>

              <span>
                Status
              </span>

              <strong>
                Mastered
              </strong>

            </div>


            <div>

              <span>
                Retest Required
              </span>

              <strong>
                No
              </strong>

            </div>


            <div>

              <span>
                Readiness
              </span>

              <strong>
                100%
              </strong>

            </div>


          </div>


          <br />


          <button
            onClick={
              nextQuestion
            }
          >

            Next Question

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* TUTOR */}
      {/* ================================================= */}

      {tutor && (

        <div className="card">


          <h2>
            {
              analysis?.test_score === 100
                ? "Concept Verification"
                : "Adaptive Tutor"
            }
          </h2>


          {analysis?.test_score !== 100 && (

            <>

              <h3>
                Progressive Hint
              </h3>


              <p>
                {
                  tutor.hint
                }
              </p>


              <h3>
                Practice Problem
              </h3>


              <p>
                {
                  tutor.practice_problem
                }
              </p>

            </>

          )}


          {analysis?.test_score === 100 && (

            <p>
              Your code passed independently. LabTwin is now checking whether you understand the exact concept before marking the topic as mastered.
            </p>

          )}


          <h3>
            Viva Question
          </h3>


          <p>
            {
              tutor.viva_question
            }
          </p>


          <h3>
            {
              analysis?.test_score === 100
                ? "Your Verified Code"
                : "Correct Your Code"
            }
          </h3>


          <textarea

            value={
              correctedCode
            }

            onChange={(e) =>
              setCorrectedCode(
                e.target.value
              )
            }

            placeholder={
              `Enter ${question?.language || "programming"} code...`
            }

          />


          <h3>
            Your Viva Answer
          </h3>


          <textarea

            value={
              vivaAnswer
            }

            onChange={(e) =>
              setVivaAnswer(
                e.target.value
              )
            }

            placeholder={
              "Explain the concept in your own words..."
            }

          />


          <button

            onClick={
              evaluateCode
            }

            disabled={
              loading ||
              !correctedCode.trim() ||
              !vivaAnswer.trim()
            }

          >

            {
              analysis?.test_score === 100
                ? "Verify Understanding"
                : "Evaluate Improvement"
            }

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* FINAL */}
      {/* ================================================= */}

      {evaluation && (

        <div className="card report">


          <h2>
            LabTwin Final Report
          </h2>


          <div className="reportGrid">


            <div>

              <span>
                Retest Score
              </span>

              <strong>
                {
                  evaluation
                    .retest_score
                }%
              </strong>

            </div>


            <div>

              <span>
                Concept Understanding
              </span>

              <strong>
                {
                  evaluation
                    .evaluation
                    .score
                }%
              </strong>

            </div>


            <div>

              <span>
                Current Topic Mastery
              </span>

              <strong>
                {
                  evaluation
                    .topic_mastery
                }%
              </strong>

            </div>


            <div>

              <span>
                Overall Lab Readiness
              </span>

              <strong>
                {
                  evaluation
                    .lab_readiness
                }%
              </strong>

            </div>


          </div>


          <h3>
            Status
          </h3>


          <p>
            <strong>
              {
                evaluation
                  .evaluation
                  .status
              }
            </strong>
          </p>


          <h3>
            Evaluator Feedback
          </h3>


          <p>
            {
              evaluation
                .evaluation
                .reason
            }
          </p>


          {
            evaluation
              .evaluation
              .missing_concepts
              ?.length > 0
            && (

              <p>
                Missing concepts:{" "}
                {
                  evaluation
                    .evaluation
                    .missing_concepts
                    .join(", ")
                }
              </p>

            )
          }


          {
            evaluation
              .evaluation
              .contradictions
              ?.length > 0
            && (

              <p>
                Conceptual contradiction:{" "}
                {
                  evaluation
                    .evaluation
                    .contradictions
                    .join(", ")
                }
              </p>

            )
          }


          {
            evaluation
              .evaluation
              .status !== "Mastered"
            && (

              <p>
                LabTwin will keep the next question focused on this exact topic until independent mastery is demonstrated.
              </p>

            )
          }


          <button
            onClick={
              nextQuestion
            }
          >

            Next Question

          </button>


        </div>

      )}



    </div>

  );
}


export default App;













