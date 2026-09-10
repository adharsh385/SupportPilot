def build_context(results):

    context_parts = []

    for result in results:

        context_parts.append(

            f"SOURCE: {result['id']}\n"
            f"TITLE: {result['title']}\n"
            f"RELEVANCE: "
            f"{result['score']:.2f}\n\n"
            f"{result['content']}"

        )

    return (

        "\n\n"
        "------------------------------"
        "\n\n"

    ).join(context_parts)


def generate_resolution(
    ticket,
    retrieved_docs
):

    if not retrieved_docs:

        return {

            "text": (

                "No sufficiently relevant "
                "knowledge-base information "
                "was found. Additional "
                "investigation is required."

            ),

            "steps": [],

            "status":
                "INSUFFICIENT_KNOWLEDGE"

        }

    steps = []
    seen = set()

    for document in retrieved_docs:

        for line in (
            document["content"]
            .splitlines()
        ):

            line = line.strip()

            if not line:
                continue

            if (
                line[0].isdigit()
                and ". " in line
            ):

                instruction = (
                    line.split(
                        ". ",
                        1
                    )[1].strip()
                )

            else:

                instruction = line

            key = instruction.lower()

            if key not in seen:

                seen.add(key)

                steps.append({

                    "instruction":
                        instruction,

                    "source":
                        f"{document['id']} – "
                        f"{document['title']}"

                })

    steps = steps[:8]

    lines = [
        "Recommended troubleshooting steps:"
    ]

    for number, step in enumerate(
        steps,
        start=1
    ):

        lines.append(
            f"{number}. "
            f"{step['instruction']}"
        )

        lines.append(
            f"   Source: "
            f"{step['source']}"
        )

    lines.append("")

    lines.append(
        "If the issue persists after "
        "the applicable steps are "
        "completed, escalate the "
        "ticket for additional "
        "investigation."
    )

    return {

        "text":
            "\n".join(lines),

        "steps":
            steps,

        "status":
            "RESOLUTION_GENERATED"

    }