def format_explain_prompt(code_snippet: str) -> str:
    return (
        "Explain this code or technical content step-by-step. "
        "Identify what it does, how it works, and what could be improved.\n\n"
        f"```python\n{code_snippet}\n```"
    )

def format_debug_prompt(broken_code: str) -> str:
    return (
        "Debug this code. Identify the exact failure points, explain why they fail, "
        "then provide a corrected version.\n\n"
        f"```python\n{broken_code}\n```"
    )
