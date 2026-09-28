import os
import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Prices are USD per 1M tokens.
MODEL_PRICING = {
    "claude-haiku-4-5": {
        "input": 0.80,
        "output": 4.00,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
    },
    # --- Azure GPT models -------------------------------------------------
    # TODO: these are PLACEHOLDERS (0.0). Replace with the actual per-1M-token
    # prices from your Azure pricing agreement/invoice before relying on the
    # cost figures for these models — as-is they will log $0.00 and silently
    # understate spend.
    "gpt-5.6-terra": {
        "input": 0.0,
        "output": 0.0,
    },
    "gpt-5.6-luna": {
        "input": 0.0,
        "output": 0.0,
    },
    "gpt-5-mini": {
        "input": 0.0,
        "output": 0.0,
    },
    "model-router": {
        "input": 0.0,
        "output": 0.0,
    },
}

TOKEN_LOG_FILE = "logs/tokens_usage.csv"


def _log_costs(input_tokens, output_tokens, model, user_id):
    pricing = MODEL_PRICING.get(model)

    if pricing is None:
        # Don't crash the request just because pricing metadata is missing
        # (e.g. a new/renamed deployment) — log a visible warning and record
        # cost as 0 so usage tracking keeps working.
        # logger.warning(
        #     f"No pricing entry for model '{model}' — logging cost as 0.0. "
        #     f"Add it to MODEL_PRICING in {__name__}."
        # )
        pricing = {"input": 0.0, "output": 0.0}

    input_cost = input_tokens * pricing["input"] / 1_000_000
    output_cost = output_tokens * pricing["output"] / 1_000_000
    total_cost = input_cost + output_cost

    os.makedirs("logs", exist_ok=True)

    with open(TOKEN_LOG_FILE, "a", newline="") as fout:
        writer = csv.writer(fout)

        if fout.tell() == 0:
            writer.writerow(
                [
                    "datetime",
                    "user_id",
                    "model",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "input_cost_usd",
                    "output_cost_usd",
                    "total_cost_usd",
                ]
            )

        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                user_id,
                model,
                input_tokens,
                output_tokens,
                input_tokens + output_tokens,
                round(input_cost, 8),
                round(output_cost, 8),
                round(total_cost, 8),
            ]
        )


def get_usage_per_day():
    """
    Aggregate usage by day and user.

    Returns:
        List[dict]
    """

    if not Path(TOKEN_LOG_FILE).exists():
        return []

    stats = defaultdict(
        lambda: {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost_usd": 0.0,
        }
    )

    with open(TOKEN_LOG_FILE, newline="") as fin:
        reader = csv.DictReader(fin)

        for row in reader:
            day = row["datetime"][:10]  # YYYY-MM-DD
            user = row["user_id"]

            key = (day, user)

            stats[key]["requests"] += 1
            stats[key]["input_tokens"] += int(row["input_tokens"])
            stats[key]["output_tokens"] += int(row["output_tokens"])
            stats[key]["total_cost_usd"] += float(row["total_cost_usd"])

    result = []

    for (day, user), values in sorted(stats.items()):
        result.append(
            {
                "date": day,
                "user_id": user,
                "requests": values["requests"],
                "input_tokens": values["input_tokens"],
                "output_tokens": values["output_tokens"],
                "total_cost_usd": round(values["total_cost_usd"], 6),
            }
        )

    return result
