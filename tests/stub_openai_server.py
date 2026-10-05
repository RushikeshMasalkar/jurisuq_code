#!/usr/bin/env python3
"""A tiny OpenAI-compatible server: lets you test the client with no model.

Purpose: prove the sampling harness, retry logic, logprob handling and the
resume path work, and let `pytest` exercise the network code, without needing a
generator installed. It returns canned legal answers and fake logprobs.

    python tests/stub_openai_server.py --port 1234
    python scripts/02_run_inference.py --set provider=openai \
        --set base_url=http://127.0.0.1:1234/v1 --set model=stub \
        --set n_samples=5 --set limit=6 --set run-id=stubcheck

It is NOT a model and must never be used for results.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWERS = [
    "The applicable provision is Section 103 of the BNS, which prescribes death or "
    "imprisonment for life, and fine.",
    "Answer: Section 302 of the IPC - death or imprisonment for life.",
    "In India today, the applicable provision is Section 105 of the BNS, which prescribes "
    "imprisonment for life, or imprisonment up to ten years, and fine.",
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):        # keep the console readable
        pass

    def _json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:            # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": "stub", "object": "model"}]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:           # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        seed = req.get("seed", 0)
        rng = random.Random(seed)
        text = ANSWERS[rng.randrange(len(ANSWERS))]
        toks = text.split()
        content = [{"token": f" {t}", "logprob": -0.05 - 0.25 * rng.random(),
                    "top_logprobs": [{"token": f" {t}", "logprob": -0.05}]} for t in toks]
        # a deliberate 8 per cent error rate, to exercise the retry path
        if rng.random() < 0.08:
            self._json({"error": "simulated server hiccup"}, 500)
            return
        time.sleep(0.01)
        self._json({
            "id": f"chatcmpl-{seed}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.get("model", "stub"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
                "logprobs": {"content": content},
            }],
            "usage": {"prompt_tokens": 40, "completion_tokens": len(toks), "total_tokens": 40 + len(toks)},
        })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=1234)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"stub OpenAI-compatible server on http://{args.host}:{args.port}/v1  (ctrl-c to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
