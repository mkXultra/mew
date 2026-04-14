import json

from .agent_runs import DEFAULT_AGENT_BACKEND, DEFAULT_AGENT_MODEL, create_agent_run
from .state import next_id, reconcile_next_ids
from .timeutil import now_iso


DEFAULT_REVIEW_MODEL = "gpt-5.1-codex-mini"

SAFE_TOOL_PROMPT_GUIDANCE = (
    "Safe local tool layer:\n"
    "- Prefer `uv run mew tool status` and `uv run mew tool git status` for workspace status.\n"
    "- Use `uv run mew tool list`, `uv run mew tool read`, and `uv run mew tool search` "
    "for bounded inspection.\n"
    "- Use `uv run mew tool test --command \"...\"` for verification when practical.\n\n"
)


def latest_task_plan(task):
    plans = task.get("plans") or []
    latest_id = task.get("latest_plan_id")
    if latest_id is not None:
        for plan in plans:
            if str(plan.get("id")) == str(latest_id):
                return plan
    return plans[-1] if plans else None


def find_task_plan(task, plan_id):
    for plan in task.get("plans") or []:
        if str(plan.get("id")) == str(plan_id):
            return plan
    return None


def build_implementation_prompt(task, plan):
    criteria = "\n".join(f"- {item}" for item in plan.get("done_criteria", []))
    return (
        "You are an implementation agent working under mew's programmer loop.\n"
        "Make focused changes for the assigned task, preserve unrelated work, run relevant checks, "
        "and report changed files and verification results.\n\n"
        f"{SAFE_TOOL_PROMPT_GUIDANCE}"
        f"Task #{task['id']}: {task.get('title')}\n"
        f"Description:\n{task.get('description') or '(none)'}\n\n"
        f"Notes:\n{task.get('notes') or '(none)'}\n\n"
        f"Plan #{plan['id']} objective:\n{plan.get('objective') or task.get('title')}\n\n"
        f"Suggested approach:\n{plan.get('approach') or '(choose the smallest safe approach)'}\n\n"
        f"Done criteria:\n{criteria or '- Implement the task safely and verify the result.'}\n"
    )


def build_review_prompt(task, implementation_run, plan=None):
    plan_text = ""
    if plan:
        criteria = "\n".join(f"- {item}" for item in plan.get("done_criteria", []))
        plan_text = (
            f"Plan #{plan['id']} objective:\n{plan.get('objective') or ''}\n\n"
            f"Done criteria:\n{criteria or '(none)'}\n\n"
        )

    verification = implementation_run.get("supervisor_verification")
    verification_text = "(none)"
    if verification:
        verification_text = json.dumps(verification, ensure_ascii=False, indent=2)

    return (
        "You are a review agent in mew's programmer loop.\n"
        "Review the implementation run result and the current workspace. "
        "Do not modify files. Return a concise report with this exact shape:\n\n"
        "STATUS: pass|needs_fix|unknown\n"
        "SUMMARY: <one paragraph>\n"
        "FINDINGS:\n"
        "- <finding or 'none'>\n"
        "FOLLOW_UP:\n"
        "- <task to create or 'none'>\n\n"
        f"Task #{task['id']}: {task.get('title')}\n"
        f"Description:\n{task.get('description') or '(none)'}\n\n"
        f"{plan_text}"
        f"Implementation run #{implementation_run['id']} status={implementation_run.get('status')}\n"
        f"Implementation result:\n{implementation_run.get('result') or implementation_run.get('stdout') or '(none)'}\n"
        f"Supervisor verification:\n{verification_text}\n"
        f"Implementation stderr:\n{implementation_run.get('stderr') or '(none)'}\n"
    )


def build_retry_prompt(task, failed_run, plan=None):
    base = build_implementation_prompt(
        task,
        plan
        or {
            "id": failed_run.get("plan_id") or "<retry>",
            "objective": task.get("description") or task.get("title"),
            "approach": "Retry the task with the smallest focused correction.",
            "done_criteria": [
                "Address the previous failure.",
                "Report changed files and verification.",
                "Preserve unrelated user changes.",
            ],
        },
    )
    return (
        f"{base}\n\n"
        f"Retry context:\n"
        f"Previous implementation run #{failed_run.get('id')} status={failed_run.get('status')}.\n"
        f"Previous result:\n{failed_run.get('result') or failed_run.get('stdout') or '(none)'}\n\n"
        f"Previous stderr:\n{failed_run.get('stderr') or '(none)'}\n\n"
        "Treat this as a retry. Fix the failure if possible, keep the change small, "
        "and explicitly report what changed since the previous run.\n"
    )


def create_task_plan(
    state,
    task,
    cwd=None,
    model=None,
    review_model=None,
    objective=None,
    approach=None,
):
    current_time = now_iso()
    plan = {
        "id": next_id(state, "plan"),
        "task_id": task["id"],
        "status": "planned",
        "backend": DEFAULT_AGENT_BACKEND,
        "model": model or task.get("agent_model") or DEFAULT_AGENT_MODEL,
        "review_model": review_model or DEFAULT_REVIEW_MODEL,
        "cwd": cwd or task.get("cwd") or ".",
        "objective": objective or task.get("description") or task.get("title") or "",
        "approach": approach or "Make the smallest focused change that satisfies the task.",
        "done_criteria": [
            "Implementation result explains changed files and verification.",
            "Relevant checks are run or skipped with a clear reason.",
            "Unrelated user changes are preserved.",
        ],
        "implementation_prompt": "",
        "review_prompt": "",
        "created_at": current_time,
        "updated_at": current_time,
    }
    plan["implementation_prompt"] = build_implementation_prompt(task, plan)
    plan["review_prompt"] = build_review_prompt(task, {"id": "<implementation-run>", "status": "pending"}, plan)
    task.setdefault("plans", []).append(plan)
    task["latest_plan_id"] = plan["id"]
    task["agent_backend"] = plan["backend"]
    task["agent_model"] = plan["model"]
    task["agent_prompt"] = plan["implementation_prompt"]
    task["cwd"] = plan["cwd"]
    task["updated_at"] = current_time
    return plan


def format_task_plan(plan):
    return (
        f"plan #{plan['id']} task=#{plan.get('task_id')} status={plan.get('status')} "
        f"backend={plan.get('backend')} model={plan.get('model')} cwd={plan.get('cwd')}"
    )


def create_implementation_run_from_plan(state, task, plan, dry_run=False):
    run = create_agent_run(
        state,
        task,
        backend=plan.get("backend") or DEFAULT_AGENT_BACKEND,
        model=plan.get("model") or DEFAULT_AGENT_MODEL,
        cwd=plan.get("cwd") or task.get("cwd") or ".",
        prompt=plan.get("implementation_prompt") or build_implementation_prompt(task, plan),
        purpose="implementation",
        plan_id=plan.get("id"),
    )
    if dry_run:
        run["status"] = "dry_run"
    plan["status"] = "dispatched" if not dry_run else "dry_run"
    plan["updated_at"] = now_iso()
    return run


def create_review_run_for_implementation(state, task, implementation_run, plan=None, model=None):
    prompt = build_review_prompt(task, implementation_run, plan)
    return create_agent_run(
        state,
        task,
        backend=DEFAULT_AGENT_BACKEND,
        model=model or (plan or {}).get("review_model") or DEFAULT_REVIEW_MODEL,
        cwd=implementation_run.get("cwd") or (plan or {}).get("cwd") or task.get("cwd") or ".",
        prompt=prompt,
        purpose="review",
        plan_id=(plan or {}).get("id"),
        parent_run_id=implementation_run.get("id"),
        review_of_run_id=implementation_run.get("id"),
    )


def create_retry_run_for_implementation(state, task, failed_run, plan=None, model=None, dry_run=False):
    run = create_agent_run(
        state,
        task,
        backend=DEFAULT_AGENT_BACKEND,
        model=model or (plan or {}).get("model") or task.get("agent_model") or DEFAULT_AGENT_MODEL,
        cwd=failed_run.get("cwd") or (plan or {}).get("cwd") or task.get("cwd") or ".",
        prompt=build_retry_prompt(task, failed_run, plan=plan),
        purpose="implementation",
        plan_id=(plan or {}).get("id") or failed_run.get("plan_id"),
        parent_run_id=failed_run.get("id"),
    )
    if dry_run:
        run["status"] = "dry_run"
    return run


def find_review_run_for_implementation(state, implementation_run_id):
    for run in state.get("agent_runs", []):
        if (
            run.get("purpose") == "review"
            and str(run.get("review_of_run_id")) == str(implementation_run_id)
        ):
            return run
    return None


def parse_review_status(text):
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.casefold().startswith("status:"):
            continue
        value = stripped.split(":", 1)[1].strip().casefold()
        normalized = value.replace("-", "_")
        if normalized == "pass":
            return "pass"
        if normalized in ("needs_fix", "needs fix", "fail", "failed"):
            return "needs_fix"
    return "unknown"


def _nonempty_string(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _extract_ai_cli_agent_message(value):
    if isinstance(value, list):
        for child in value:
            found = _extract_ai_cli_agent_message(child)
            if found:
                return found
        return ""

    if not isinstance(value, dict):
        return ""

    for output_key in ("agentOutput", "agent_output"):
        output = value.get(output_key)
        if isinstance(output, dict):
            for message_key in ("message", "text", "content", "output"):
                found = _nonempty_string(output.get(message_key))
                if found:
                    return found
        found = _nonempty_string(output)
        if found:
            return found

    for message_key in ("message", "text", "content", "output"):
        found = _nonempty_string(value.get(message_key))
        if found:
            return found

    for child_key in ("result", "data"):
        found = _extract_ai_cli_agent_message(value.get(child_key))
        if found:
            return found

    return ""


def extract_review_text(review_run):
    for key in ("result", "stdout"):
        raw = review_run.get(key)
        if not _nonempty_string(raw):
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()

        message = _extract_ai_cli_agent_message(parsed)
        if message:
            return message

        # ai-cli JSON includes the prompt, which contains the review template.
        # Do not scan the raw JSON string or the template can be mistaken for
        # an actual STATUS line.
    return ""


def extract_follow_up_text(text):
    lines = (text or "").splitlines()
    in_follow_up = False
    collected = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FOLLOW_UP"):
            in_follow_up = True
            continue
        if in_follow_up and stripped.upper().startswith(("STATUS:", "SUMMARY:", "FINDINGS:")):
            break
        if in_follow_up and stripped:
            item = stripped.lstrip("- ").strip()
            if item and item.casefold() != "none":
                collected.append(item)
    return "\n".join(collected).strip()


def create_follow_up_task_from_review(state, task, review_run):
    followup_task_id = review_run.get("followup_task_id")
    if followup_task_id is not None:
        for existing in state.get("tasks", []):
            if str(existing.get("id")) == str(followup_task_id):
                return existing, review_run.get("review_status") or "unknown"

    result = extract_review_text(review_run)
    status = parse_review_status(result)
    review_run["review_status"] = status
    task.setdefault("notes", "")
    current_time = now_iso()
    task["notes"] = (
        f"{task['notes'].rstrip()}\n{current_time} review run #{review_run['id']}: {status}"
    ).strip()
    task["updated_at"] = current_time
    review_run["followup_processed_at"] = current_time
    review_run["updated_at"] = current_time

    follow_up = extract_follow_up_text(result)
    if status == "needs_fix" and not follow_up:
        follow_up = result or f"Review run #{review_run['id']} reported needs_fix without follow-up details."
    if not follow_up or status == "pass":
        return None, status

    if status == "needs_fix" and task.get("status") == "done":
        task["status"] = "blocked"

    reconcile_next_ids(state)
    new_task = {
        "id": next_id(state, "task"),
        "title": f"Follow up review #{review_run['id']} for task #{task['id']}",
        "description": follow_up,
        "status": "todo",
        "priority": "normal",
        "notes": f"Created from review run #{review_run['id']} of task #{task['id']}.",
        "command": "",
        "cwd": task.get("cwd") or "",
        "auto_execute": False,
        "agent_backend": "",
        "agent_model": "",
        "agent_prompt": "",
        "agent_run_id": None,
        "plans": [],
        "latest_plan_id": None,
        "runs": [],
        "created_at": current_time,
        "updated_at": current_time,
    }
    state["tasks"].append(new_task)
    review_run["followup_task_id"] = new_task["id"]
    review_run["updated_at"] = current_time
    return new_task, status
