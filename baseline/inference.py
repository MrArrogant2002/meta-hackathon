"""
LLM-based baseline inference script using HuggingFace Inference API.

Usage:
    python -m baseline.inference --host http://localhost:7860
    python -m baseline.inference --host http://localhost:7860 --model Qwen/Qwen2.5-Coder-7B-Instruct
    python -m baseline.inference --host https://your-space.hf.space

Requires HF_TOKEN environment variable for gated models.
"""
import argparse
import json
import os
import re
import sys
import requests
from huggingface_hub import InferenceClient

DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

SYSTEM_PROMPT = (
    "You are an expert SQL developer. Given a broken SQL query and a database schema, "
    "you must fix or optimize the query. "
    "Respond with ONLY the corrected SQL query, no explanation, no markdown code blocks."
)


def extract_sql(text: str) -> str:
    """Extract SQL from model response, stripping markdown fences if present."""
    # Remove ```sql ... ``` or ``` ... ```
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```', '', text)
    return text.strip()


def call_llm(client: InferenceClient, model: str, prompt: str) -> str:
    response = client.chat_completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        temperature=0.0,  # Deterministic output
    )
    return response.choices[0].message.content.strip()


def run_task(host: str, task_id: str, client: InferenceClient, model: str) -> dict:
    # Reset
    r = requests.post(f"{host}/reset", json={"task_id": task_id})
    r.raise_for_status()
    reset_data = r.json()
    session_id = reset_data["session_id"]
    obs = reset_data["observation"]

    print(f"\n{'='*60}")
    print(f"Task: {task_id}")
    print(f"Session: {session_id}")
    print(f"Description: {obs['task_description']}")
    print(f"Broken query:\n{obs['broken_query']}")

    headers = {"X-Session-Id": session_id}
    best_score = 0.0
    final_breakdown = {}
    steps_taken = 0
    final_query = obs["broken_query"]

    for step_num in range(obs["max_steps"]):
        # Build prompt with current observation
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

        # Call LLM
        fixed_sql = extract_sql(call_llm(client, model, prompt))
        print(f"\nStep {step_num + 1}: Submitting:\n{fixed_sql}")

        # Step in environment
        r = requests.post(
            f"{host}/step",
            json={"sql_query": fixed_sql},
            headers=headers,
        )
        r.raise_for_status()
        step_data = r.json()

        reward = step_data["reward"]
        info = step_data["info"]
        obs = step_data["observation"]
        steps_taken = step_num + 1
        final_query = fixed_sql

        print(f"  Score: {info.get('grader_score', 0):.3f} | Reward: {reward['value']:.3f}")
        print(f"  Breakdown: {reward['components']}")

        best_score = info.get("best_score_so_far", best_score)
        final_breakdown = reward["components"]

        if step_data["done"]:
            print(f"  Episode done: {'SOLVED' if info.get('solved') else 'TIMEOUT'}")
            break

    return {
        "task_id": task_id,
        "score": best_score,
        "steps_taken": steps_taken,
        "final_query": final_query,
        "breakdown": final_breakdown,
        "solved": best_score >= 0.8,
    }


def main():
    parser = argparse.ArgumentParser(description="Run LLM baseline against SQL Query Env")
    parser.add_argument("--host", default="http://localhost:7860", help="Environment API host")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HuggingFace model ID")
    parser.add_argument("--tasks", nargs="+",
                        default=["easy_syntax_fix", "medium_logic_fix", "hard_optimization"],
                        help="Task IDs to run")
    args = parser.parse_args()

    hf_token = os.environ.get("HF_TOKEN")
    client = InferenceClient(token=hf_token)

    print(f"Running baseline with model: {args.model}")
    print(f"Environment host: {args.host}")

    all_results = {}
    for task_id in args.tasks:
        result = run_task(args.host, task_id, client, args.model)
        all_results[task_id] = result

    print("\n" + "="*60)
    print("BASELINE RESULTS SUMMARY")
    print("="*60)
    total_score = 0.0
    for task_id, result in all_results.items():
        print(f"  {task_id}: {result['score']:.3f} ({'SOLVED' if result['solved'] else 'FAILED'}) in {result['steps_taken']} steps")
        total_score += result["score"]
    avg_score = total_score / len(all_results) if all_results else 0.0
    print(f"\nAverage score: {avg_score:.3f}")

    # Save results
    output = {
        "model": args.model,
        "host": args.host,
        "results": all_results,
        "average_score": avg_score,
    }
    with open("baseline_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nResults saved to baseline_results.json")

    return 0 if avg_score >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
