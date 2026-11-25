"""Turns the Claude Code transcript into chat/full-chat.md.

  python3 chat/export_chat.py ~/.claude/projects/<project>/<session>.jsonl

Every message I typed and everything the AI said or did is kept, in order.
Removed, and marked where it happens: e-mail addresses, GitHub account names in
login checks, the word lists the AI searched for when checking this file for
private data, the AI's private notes about me from unrelated projects, and the
home folder name. When a chat grows too long the app writes its own summary of
it; that is marked as the app's, because I did not type it. Long tool output is
cut at LIMIT characters and says so. The AI's hidden reasoning and the app's
system messages are not part of the conversation and are not included.
"""
import json
import re
import sys
from pathlib import Path

LIMIT = 3500
MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
OUT = Path(__file__).with_name("full-chat.md")
hidden = set()  # tool calls whose content is private


def clean(text):
    text = re.sub(r"<system-reminder.*?</system-reminder[^>]*>", "", text, flags=re.S)
    text = MAIL.sub(lambda m: m[0] if m[0].endswith((".py", ".jpg", "example")) else "[e-mail removed]", text)
    text = re.sub(r"(grep -[a-zA-Z]*Ei )(\"[^\"]*\"|'[^']*')", r"\1[private word list removed]", text)
    text = re.sub(r"(github\.com account )[A-Za-z0-9-]+", r"\1[account name removed]", text)
    return text.replace(str(Path.home()), "~").strip()


def fence(text, lang=""):
    tick = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
    return f"{tick}{lang}\n{text}\n{tick}"


def cut(text):
    return text if len(text) <= LIMIT else text[:LIMIT] + f"\n[... {len(text) - LIMIT} more characters cut]"


def private(block):
    return "/memory" in json.dumps(block.get("input", {})) and ".claude/projects" in json.dumps(block.get("input", {}))


def main(path):
    out, me, ai = [], 0, 0
    for line in Path(path).read_text().splitlines():
        d = json.loads(line)
        if d.get("type") not in ("user", "assistant") or d.get("isMeta"):
            continue
        content = d["message"]["content"]
        when = (d.get("timestamp") or "")[:16].replace("T", " ")
        if d.get("isCompactSummary"):
            out.append(f"*(the chat grew too long and the app summarised it here, {when})*\n")
            continue
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for b in blocks:
            if b["type"] == "text":
                text = clean(b["text"])
                if not text:
                    continue
                if d["type"] == "user" and text.startswith(("[SYSTEM NOTIFICATION", "<task-notification", "Another Claude session")):
                    out.append(f"*(app notification, {when})*\n")
                elif d["type"] == "user":
                    me += 1
                    out.append(f"## Me ({when} UTC)\n\n" + "\n".join("> " + x for x in text.splitlines()) + "\n")
                else:
                    ai += 1
                    out.append(f"### AI ({when} UTC)\n\n{text}\n")
            elif b["type"] == "tool_use":
                if private(b):
                    hidden.add(b["id"])
                    out.append(f"**AI used {b['name']}** [private notes from other projects, removed]\n")
                    continue
                inp = b["input"]
                body = inp.get("command") or inp.get("content") or json.dumps(inp, indent=1, ensure_ascii=False)
                head = inp.get("description") or inp.get("file_path") or ""
                out.append(f"**AI used {b['name']}** {clean(str(head))}\n\n{fence(cut(clean(body)))}\n")
            elif b["type"] == "tool_result" and b.get("tool_use_id") not in hidden:
                c = b.get("content")
                text = c if isinstance(c, str) else "\n".join(x.get("text", f"[{x.get('type')}]") for x in c or [])
                text = clean(text)
                if text:
                    out.append(f"<details><summary>result</summary>\n\n{fence(cut(text))}\n\n</details>\n")
    OUT.write_text(f"# Full chat history\n\nExported from Claude Code with chat/export_chat.py. {me} messages from me, "
                   f"{ai} from the AI. What was removed is described in that script.\n\n" + "\n".join(out))
    print(OUT, f"{OUT.stat().st_size // 1024} KB", me, "from me,", ai, "from the AI")


if __name__ == "__main__":
    main(sys.argv[1])
