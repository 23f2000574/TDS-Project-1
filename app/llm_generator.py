import os
import base64
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Gemini API Configuration ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠️ GEMINI_API_KEY not found in environment variables.")

TMP_DIR = Path("/tmp/llm_attachments")
TMP_DIR.mkdir(parents=True, exist_ok=True)

def decode_attachments(attachments):
    """
    attachments: list of {name, url: data:<mime>;base64,<b64>}
    Saves files into /tmp/llm_attachments/<name>
    Returns list of dicts: {"name": name, "path": "/tmp/..", "mime": mime, "size": n}
    """
    saved = []
    for att in attachments or []:
        name = att.get("name") or "attachment"
        url = att.get("url", "")
        if not url.startswith("data:"):
            continue
        try:
            header, b64data = url.split(",", 1)
            mime = header.split(";")[0].replace("data:", "")
            data = base64.b64decode(b64data)
            path = TMP_DIR / name
            with open(path, "wb") as f:
                f.write(data)
            saved.append({
                "name": name,
                "path": str(path),
                "mime": mime,
                "size": len(data)
            })
        except Exception as e:
            print("Failed to decode attachment", name, e)
    return saved

def summarize_attachment_meta(saved):
    """
    saved is list from decode_attachments.
    Returns a short human-readable summary string for the prompt.
    """
    summaries = []
    for s in saved:
        nm = s["name"]
        p = s["path"]
        mime = s.get("mime", "")
        try:
            if mime.startswith("text") or nm.endswith((".md", ".txt", ".json", ".csv")):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    if nm.endswith(".csv"):
                        lines = [next(f).strip() for _ in range(3)]
                        preview = "\n".join(lines)
                    else:
                        data = f.read(1000)
                        preview = data.replace("\n", "\n")[:1000]
                summaries.append(f"- {nm} ({mime}): preview: {preview}")
            else:
                summaries.append(f"- {nm} ({mime}): {s['size']} bytes")
        except Exception as e:
            summaries.append(f"- {nm} ({mime}): (could not read preview: {e})")
    return "\n".join(summaries)

def _strip_code_block(text: str) -> str:
    """
    If text is inside triple-backticks, return inner contents. Otherwise return text as-is.
    The first line after ``` often contains the language, which we strip.
    """
    if "```" in text:
        # Find the first occurrence of ``` and start from the next line
        start = text.find("```") + 3
        # If there's a language hint, move past it
        if text[start] != '\n':
            start = text.find('\n', start) + 1
        # Find the closing ```
        end = text.rfind("```")
        if end > start:
            return text[start:end].strip()
    return text.strip()


def generate_readme_fallback(brief: str, checks=None, attachments_meta=None, round_num=1):
    checks_text = "\n".join(checks or [])
    att_text = attachments_meta or ""
    return f"""# Auto-generated README (Round {round_num})

**Project brief:** {brief}

**Attachments:**
{att_text}

**Checks to meet:**
{checks_text}

## Setup
1. Open `index.html` in a browser.
2. No build steps required.

## Notes
This README was generated as a fallback because the LLM did not return an explicit README.
"""

def generate_app_code(brief: str, attachments=None, checks=None, round_num=1, prev_readme=None):
    """
    Generate or revise an app using the Gemini API.
    - round_num=1: build from scratch
    - round_num=2: refactor based on new brief and previous README/code
    """
    saved = decode_attachments(attachments or [])
    attachments_meta = summarize_attachment_meta(saved)

    context_note = ""
    if round_num == 2 and prev_readme:
        context_note = f"\n### Previous README.md:\n{prev_readme}\n\nRevise and enhance this project according to the new brief below.\n"

    user_prompt = f"""
You are a professional web developer assistant.

### Round
{round_num}

### Task
{brief}

{context_note}

### Attachments (if any)
{attachments_meta}

### Evaluation checks
{checks or []}

### Output format rules:
1. Produce a complete web app (HTML/JS/CSS inline if needed) satisfying the brief.
2. Your output MUST contain two markdown code blocks ONLY: one for `index.html` and one for `README.md`.
3. The `README.md` block must start on a new line immediately after the `index.html` block.
4. The `README.md` must include: Overview, Setup, and Usage sections. If Round 2, describe improvements.
5. Example format:
   ```html
   <!DOCTYPE html>
   ...
   ```
   ```markdown
   # Project README
   ...
   ```
6. Do not include any other text or commentary outside of these two code blocks.
"""

    try:
        if not genai.get_model('models/gemini-2.5-flash-preview-09-2025'):
             raise Exception("Gemini model not available.")

        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        response = model.generate_content(user_prompt)
        text = response.text or ""
        print("✅ Generated code using Gemini API.")
    except Exception as e:
        print(f"⚠️ Gemini API failed, using fallback HTML instead: {e}")
        text = f"""
```html
<html>
  <head><title>Fallback App</title></head>
  <body>
    <h1>Hello (fallback)</h1>
    <p>This app was generated as a fallback because the Gemini API failed. Brief: {brief}</p>
  </body>
</html>
```
```markdown
{generate_readme_fallback(brief, checks, attachments_meta, round_num)}
```
"""

    # Gemini often returns two distinct markdown blocks.
    parts = text.split("```")
    if len(parts) >= 5: # Should be ```html\n...\n```\n```markdown\n...\n```
        code_part = "```" + parts[1] + "```"
        readme_part = "```" + parts[3] + "```"
        code_part = _strip_code_block(code_part)
        readme_part = _strip_code_block(readme_part)
    else:
        # Fallback if the format is unexpected
        code_part = _strip_code_block(text)
        readme_part = generate_readme_fallback(brief, checks, attachments_meta, round_num)


    files = {"index.html": code_part, "README.md": readme_part}
    return {"files": files, "attachments": saved}
