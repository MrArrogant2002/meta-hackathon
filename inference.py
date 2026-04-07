"""
Inference Script for SQL Query Debugging Environment
======================================================

MANDATORY
- Before submitting, ensure the following variables are defined in your environment configuration:
  API_BASE_URL   The API endpoint for the LLM.
  MODEL_NAME     The model identifier to use for inference.
  HF_TOKEN       Your Hugging Face / API key.
- Defaults are set for API_BASE_URL and MODEL_NAME
- The inference script must be named `inference.py` and placed in the root directory of the project
- Participants must use OpenAI Client for all LLM calls using above variables

STDOUT FORMAT
- The script must emit exactly three line types to stdout, in this order:

  [START] task=<task_name> env=<benchmark> model=<model_name>
  [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
  [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>

  Rules:
  - One [START] line at episode begin.
  - One [STEP] line per step, immediately after env.step() returns.
  - One [END] line after env.close(), always emitted (even on exception).
  - reward and rewards are formatted to 2 decimal places.
  - done and success are lowercase booleans: true or false.
  - error is the raw last_action_error string, or null if none.
  - All fields on a single line with no newlines within a line.
  - Each tasks should return score in [0, 1]
"""

import os
import re
import sys
from typing import List, Optional
import requests
from openai import OpenAI

# Load .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required in production (HF Spaces injects secrets)

# Environment variables with defaults
# For HF Spaces: Set HF_TOKEN as a Space secret in Settings
# For local dev: Create .env file with HF_TOKEN=your_token
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")
ENV_HOST = os.getenv("ENV_HOST", "http://localhost:7860")
BENCHMARK = "sql-query-debugging"

# Task configuration
TASKS = ["easy_syntax_fix", "medium_logic_fix", "hard_optimization"]
MAX_STEPS_PER_TASK = {"easy_syntax_fix": 5, "medium_logic_fix": 8, "hard_optimization": 10}
TEMPERATURE = 0.0  # Deterministic
MAX_TOKENS = 512

SYSTEM_PROMPT = (
    "You are an expert SQL developer. Given a broken SQL query and a database schema, "
    "you must fix or optimize the query. "
    "Respond with ONLY the corrected SQL query, no explanation, no markdown code blocks."
)


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    # Escape action string for single-line output
    action_clean = action.replace('\n', ' ').replace('\r', ' ')[:100]
    print(
        f"[STEP] step={step} action={action_clean} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def extract_sql(text: str) -> str:
    """Extract SQL from model response, stripping markdown fences if present."""
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```', '', text)
    return text.strip()


def call_llm(client: OpenAI, prompt: str) -> str:
    """Call LLM using OpenAI client."""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()
        return text if text else ""
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return ""


def run_task(task_id: str, client: OpenAI) -> dict:
    """Run a single task and return results."""
    max_steps = MAX_STEPS_PER_TASK.get(task_id, 5)
    
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
    
    rewards: List[float] = []
    steps_taken = 0
    score = 0.001  # Must be > 0.0 for Phase 2 validation
    success = False
    
    try:
        # Reset environment
        r = requests.post(f"{ENV_HOST}/reset", json={"task_id": task_id}, timeout=30)
        r.raise_for_status()
        reset_data = r.json()
        session_id = reset_data["session_id"]
        obs = reset_data["observation"]
        
        headers = {"X-Session-Id": session_id}
        
        for step_num in range(1, max_steps + 1):
            if obs.get("done", False):
                break
            
            # Build prompt
            prompt = (
                f"Database schema:\n{obs['schema_info']}\n\n"
                f"Task: {obs['task_description']}\n\n"
                f"Broken query:\n{obs['broken_query']}\n\n"
            )
            if obs.get("hint"):
                prompt += f"Hint: {obs['hint']}\n\n"
            if obs.get("last_execution_result") and not obs["last_execution_result"].get("success"):
                prompt += f"Previous error: {obs['last_execution_result'].get('error')}\n\n"
            prompt += "Fix or optimize the broken query above. Return ONLY the corrected SQL:"
            
            # Get LLM response
            fixed_sql = extract_sql(call_llm(client, prompt))
            if not fixed_sql:
                fixed_sql = obs['broken_query']  # Fallback
            
            # Step in environment
            try:
                r = requests.post(
                    f"{ENV_HOST}/step",
                    json={"sql_query": fixed_sql},
                    headers=headers,
                    timeout=30,
                )
                r.raise_for_status()
                step_data = r.json()
            except Exception as e:
                error_msg = str(e)
                log_step(step=step_num, action=fixed_sql, reward=0.0, done=True, error=error_msg)
                break
            
            reward_val = step_data["reward"]["value"]
            done = step_data["done"]
            info = step_data["info"]
            obs = step_data["observation"]
            error = None
            
            rewards.append(reward_val)
            steps_taken = step_num
            
            log_step(step=step_num, action=fixed_sql, reward=reward_val, done=done, error=error)
            
            score = info.get("best_score_so_far", score)
            
            if done:
                success = info.get("solved", False)
                break
        
        # Clamp score to (0, 1) - strictly between, never exactly 0.0 or 1.0
        score = max(0.001, min(score, 0.999))
        
    except Exception as e:
        print(f"[DEBUG] Task error: {e}", flush=True)
    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    
    return {
        "task_id": task_id,
        "score": score,
        "success": success,
        "steps_taken": steps_taken,
    }


def main() -> int:
    """Run baseline inference on all tasks."""
    # Initialize OpenAI client
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    
    print(f"[INFO] Running baseline with model: {MODEL_NAME}", flush=True)
    print(f"[INFO] Environment host: {ENV_HOST}", flush=True)
    print(f"[INFO] Tasks: {TASKS}", flush=True)
    print("", flush=True)
    
    all_results = {}
    total_score = 0.0
    
    for task_id in TASKS:
        result = run_task(task_id, client)
        all_results[task_id] = result
        total_score += result["score"]
        print("", flush=True)  # Blank line between tasks
    
    # Calculate average
    avg_score = total_score / len(TASKS) if TASKS else 0.0
    
    print("="*60, flush=True)
    print("BASELINE RESULTS SUMMARY", flush=True)
    print("="*60, flush=True)
    for task_id, result in all_results.items():
        status = "SOLVED" if result["success"] else "FAILED"
        print(f"  {task_id}: {result['score']:.2f} ({status}) in {result['steps_taken']} steps", flush=True)
    print(f"\nAverage score: {avg_score:.2f}", flush=True)
    print("="*60, flush=True)
    
    # Return 0 if successful (avg >= 0.1), 1 otherwise
    return 0 if avg_score >= 0.1 else 1


if __name__ == "__main__":
    sys.exit(main())
