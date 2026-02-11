from flask import Flask, render_template, request

app = Flask(__name__)

def fake_extract(user_text: str):
    """
    Test extraction function.
    This will later be replaced with ChatGPT API logic.
    """

    qs_output = (
        "# Demo QuickStatements\n"
        "Q123\tP31\tQ456\n"
        "Q123\tP1476\t\"Example title\"\n"
    )

    explain_output = (
        "Explanation (Demo)\n"
        "----------------------------------\n"
        "A possible relation was detected based on input text.\n\n"
        "Evidence snippet:\n"
        f"{user_text[:300]}\n\n"
        "Confidence: Low\n"
    )

    return qs_output, explain_output


@app.route("/", methods=["GET", "POST"])
def index():
    input_text = ""
    qs_output = ""
    explain_output = ""

    if request.method == "POST":
        input_text = request.form.get("input_text", "")
        qs_output, explain_output = fake_extract(input_text)

    return render_template(
        "index.html",
        input_text=input_text,
        qs_output=qs_output,
        explain_output=explain_output
    )


if __name__ == "__main__":
    app.run(debug=True)
