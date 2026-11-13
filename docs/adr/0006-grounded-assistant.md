# A grounded Gemini Assistant, despite "no chatbot"

The original handoff ruled out a chatbot so that the text could never contradict the map. We are adding a Gemini-backed Assistant anyway, but it is grounded. Its only context is the current Showcase Site or Analysis: manifest, statistics, rule-based insights and Model card. It may quote numbers from that context but never compute new ones. It carries the "prototype" Status. The API key stays server-side in `api/`, and the model name is a config value (`gemini-3.6-flash`; Gemini 2.0 Flash was shut down on 2026-06-01).
