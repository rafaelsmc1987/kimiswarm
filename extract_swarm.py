# -*- coding: utf-8 -*-
"""
Extrai dados estruturados do kimiagents.har para análise do Swarm do Kimi.
Produz arquivos em ./swarm_analysis/ usados pelos agentes de análise.
"""
import json
import os
from collections import Counter

HAR = "kimiagents.har"
OUT = "swarm_analysis"
os.makedirs(OUT, exist_ok=True)

with open(HAR, "r", encoding="utf-8") as f:
    har = json.load(f)
entries = har["log"]["entries"]


def decode_stream(txt):
    """Decodifica framing do Connect protocol: [1 byte flag][4 bytes len BE][payload]."""
    out = []
    i = 0
    n = len(txt)
    b = txt.encode("latin1")
    while i + 5 <= n:
        flag = b[i]
        ln = int.from_bytes(b[i + 1:i + 5], "big")
        payload = txt[i + 5:i + 5 + ln]
        out.append((flag, ln, payload))
        i += 5 + ln
    return out


# ---------------------------------------------------------------------------
# 1. Lista final de agents
# ---------------------------------------------------------------------------
best = max(
    [i for i, e in enumerate(entries) if "ListAgents" in e["request"]["url"] and e["response"]["status"] == 200],
    key=lambda i: len(entries[i]["response"]["content"]["text"]),
)
agents = json.loads(entries[best]["response"]["content"]["text"])["agents"]
agents.sort(key=lambda a: a.get("index", 0))
with open(f"{OUT}/agents.json", "w", encoding="utf-8") as fh:
    json.dump(agents, fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 2. Chat request (início do swarm) + chat messages
# ---------------------------------------------------------------------------
chat_req_text = entries[1213]["request"]["postData"]["text"]
i0 = chat_req_text.find('{"scenario"')
chat_request = json.loads(chat_req_text[i0:])
with open(f"{OUT}/chat_request.json", "w", encoding="utf-8") as fh:
    json.dump(chat_request, fh, ensure_ascii=False, indent=2)

chat_messages = json.loads(entries[1304]["response"]["content"]["text"])
with open(f"{OUT}/chat_messages.json", "w", encoding="utf-8") as fh:
    json.dump(chat_messages, fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 3. Streams do orquestrador (ResumeChat + SubscribeMessageStream grandes)
# ---------------------------------------------------------------------------
stream_events = []  # cada: (source, seq, op, mask, json_obj)
for src, idx in [("resume", 1341), ("subscribe", 1586)]:
    txt = entries[idx]["response"]["content"]["text"]
    for seq, (flag, ln, payload) in enumerate(decode_stream(txt)):
        try:
            j = json.loads(payload)
        except Exception:
            continue
        stream_events.append((src, seq, j))

# subagent spawn / agentMessage / tool calls (com args completos)
spawns = []
agent_msgs = []
tool_calls = []
think_summaries = []
texts = []
for src, seq, j in stream_events:
    mask = str(j.get("mask", ""))
    if "subagent" in mask:
        spawns.append(j)
    if "agentMessage" in mask:
        agent_msgs.append(j)
    if j.get("op") == "set" and "tool.toolCallId" in mask and "tool.args" in mask:
        tool_calls.append(j)
    if "block.think.summary" in mask and j.get("op") == "set":
        think_summaries.append(j)

with open(f"{OUT}/stream_subagent_spawns.json", "w", encoding="utf-8") as fh:
    json.dump(spawns, fh, ensure_ascii=False, indent=2)
with open(f"{OUT}/stream_agent_messages.json", "w", encoding="utf-8") as fh:
    json.dump(agent_msgs, fh, ensure_ascii=False, indent=2)
with open(f"{OUT}/stream_tool_calls.json", "w", encoding="utf-8") as fh:
    json.dump(tool_calls, fh, ensure_ascii=False, indent=2)
with open(f"{OUT}/stream_think_summaries.json", "w", encoding="utf-8") as fh:
    json.dump(think_summaries, fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 4. Transcrições dos subagents (ListAgentMessages)
# ---------------------------------------------------------------------------
agent_transcripts = {}
for e in entries:
    if "ListAgentMessages" in e["request"]["url"] and e["response"]["status"] == 200:
        body = e["response"]["content"]["text"]
        if len(body) < 1000:
            continue
        try:
            d = json.loads(body)
        except Exception:
            continue
        agent_id = e["request"]["postData"]["text"]
        # key by agent_id extracted from request
        import re
        m = re.search(r'"agent_id":"([^"]+)"', agent_id)
        aid = m.group(1) if m else "unknown"
        agent_transcripts[aid] = d

with open(f"{OUT}/agent_transcripts.json", "w", encoding="utf-8") as fh:
    json.dump(agent_transcripts, fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 5. Ferramentas usadas por subagents
# ---------------------------------------------------------------------------
tools = Counter()


def walk(o):
    if isinstance(o, dict):
        t = o.get("tool")
        if isinstance(t, dict) and "name" in t:
            tools[t["name"]] += 1
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


for e in entries:
    if "ListAgentMessages" in e["request"]["url"] and e["response"]["status"] == 200:
        try:
            walk(json.loads(e["response"]["content"]["text"]))
        except Exception:
            pass

with open(f"{OUT}/tool_usage.json", "w", encoding="utf-8") as fh:
    json.dump(dict(tools.most_common()), fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 6. Output files (OKCService)
# ---------------------------------------------------------------------------
output_files = {}
for e in entries:
    u = e["request"]["url"]
    if ("GetOutputFileTree" in u or "GetManifest" in u or "output-files" in u) and e["response"]["status"] == 200:
        c = e["response"].get("content", {})
        body = c.get("text", "") if isinstance(c, dict) else ""
        output_files[u.split("?")[0]] = body

with open(f"{OUT}/output_files.json", "w", encoding="utf-8") as fh:
    json.dump(output_files, fh, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# 7. Resumo
# ---------------------------------------------------------------------------
summary = {
    "num_agents": len(agents),
    "agent_types": dict(Counter(a.get("type") for a in agents)),
    "agent_statuses": dict(Counter(a.get("status") for a in agents)),
    "num_stream_events": len(stream_events),
    "num_subagent_spawns": len(spawns),
    "num_agent_messages": len(agent_msgs),
    "num_tool_calls": len(tool_calls),
    "num_think_summaries": len(think_summaries),
    "num_agent_transcripts": len(agent_transcripts),
    "tools_used": dict(tools.most_common()),
}
with open(f"{OUT}/summary.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)

print(json.dumps(summary, ensure_ascii=False, indent=2))
print("Arquivos escritos em", os.path.abspath(OUT))
