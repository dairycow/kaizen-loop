def build_iteration_prompt(
    n: int,
    run_id: str,
    prompt: str,
    stop_when: str | None = None,
) -> str:
    output_fields = [
        "- success: true if you made a meaningful contribution. false means changes should be discarded",
        "- summary: concise one-sentence summary of the accomplishment",
        "- key_changes_made: array of descriptions of key changes",
        "- key_learnings: array of new learnings informative for future iterations",
    ]

    if stop_when is not None:
        output_fields.append(
            "- should_fully_stop: set true ONLY when the stop condition is fully met"
        )

    stop_section = ""
    if stop_when is not None:
        stop_section = (
            f"\n\n## Stop Condition\n\n"
            f"The user configured: {stop_when}\n"
            f"If this condition is fully met, set should_fully_stop=true."
        )

    return (
        f"You are working autonomously towards an objective.\n"
        f"This is iteration {n}. Each iteration makes one incremental step.\n\n"
        f"## Instructions\n\n"
        f"1. Read .kaizen/runs/{run_id}/notes.md to understand prior work. Do NOT modify notes.md\n"
        f"2. Identify the next smallest verifiable unit of work\n"
        f"3. If a solution didn't move the needle, document learnings and set success=false\n"
        f"4. If you made code changes, run build/tests/linters if available. Do NOT make git commits\n"
        f"5. Stop any background processes before finishing\n\n"
        f"## Output\n\n"
        f"When finished, the structured output tool will prompt you for these fields:\n"
        f"{'\n'.join(output_fields)}\n"
        f"{stop_section}\n\n"
        f"## Objective\n\n{prompt}"
    )
