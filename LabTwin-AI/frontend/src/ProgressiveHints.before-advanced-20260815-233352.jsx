import { useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000/api";

function ProgressiveHints({
  problem,
  conceptKey,
  misconception,
  firstHint
}) {

  const [level, setLevel] = useState(1);

  const [hint, setHint] = useState(
    firstHint || ""
  );

  const [loading, setLoading] =
    useState(false);


  const nextHint = async () => {

    if (level >= 3) {
      return;
    }


    try {

      setLoading(true);

      const nextLevel =
        level + 1;


      const response =
        await axios.post(

          `${API}/progressive-hint/`,

          {
            problem:
              problem,

            concept_key:
              conceptKey,

            misconception:
              misconception,

            level:
              nextLevel
          }

        );


      setHint(
        response.data.hint
      );

      setLevel(
        nextLevel
      );


    } catch (error) {

      console.error(
        error
      );

      alert(
        "Could not generate another hint."
      );

    } finally {

      setLoading(false);

    }
  };


  return (

    <div>

      <h3>
        Progressive Hint
      </h3>


      <div className="adaptiveBox">

        <strong>
          Hint Level {level} of 3
        </strong>

        <p>
          {hint}
        </p>

      </div>


      {level < 3 && (

        <button
          onClick={
            nextHint
          }
          disabled={
            loading
          }
        >

          {
            loading
              ? "Generating Hint..."
              : `Need More Help - Hint ${level + 1}`
          }

        </button>

      )}


      {level === 3 && (

        <p
          style={{
            marginTop: "12px",
            fontWeight: "600"
          }}
        >
          Maximum hint level reached. Try correcting
          the program using the guidance above.
        </p>

      )}

    </div>

  );
}


export default ProgressiveHints;
