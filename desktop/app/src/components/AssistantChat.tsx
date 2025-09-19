import { ReactNode, useEffect, useRef, useState } from "react";
import api, { API_BASE, GET } from "../api";

type Msg = {
  role: "user" | "assistant";
  content: string;
  saved?: boolean;
  settingsApplied?: boolean;
};

const STORAGE_KEY = "assistant.chat.ui";
const SAVED_SIG_KEY = "assistant.chat.saved_signatures";

function messageSignature(msg: Msg): string {
  return `${msg.role}|${msg.content || ""}`;
}

function renderRichMessage(content: string): ReactNode {
  const normalized = (content || "").replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  let key = 0;
  const nextKey = () => `k${key++}`;

  const renderInline = (text: string): ReactNode[] => {
    const parts = text.split(/(\*\*[^*]+\*\*)/).filter(Boolean);
    return parts.map(part => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return <strong key={nextKey()}>{part.slice(2, -2)}</strong>;
      }
      return <span key={nextKey()}>{part}</span>;
    });
  };

  const nodes: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: { type: "ul" | "ol"; items: string[]; start?: number } | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const children: ReactNode[] = [];
    paragraph.forEach((line, idx) => {
      if (idx > 0) children.push(<br key={nextKey()} />);
      renderInline(line).forEach(node => children.push(node));
    });
    nodes.push(<p key={nextKey()}>{children}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (!list) return;
    if (list.type === "ol") {
      nodes.push(
        <ol key={nextKey()} start={list.start}>
          {list.items.map(item => (
            <li key={nextKey()}>{renderInline(item)}</li>
          ))}
        </ol>
      );
    } else {
      nodes.push(
        <ul key={nextKey()}>
          {list.items.map(item => (
            <li key={nextKey()}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    }
    list = null;
  };

  lines.forEach(rawLine => {
    const line = rawLine.replace(/\t/g, " ");
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }
    const ordered = trimmed.match(/^(\d+)[.)]\s*(.+)$/);
    const bullet = trimmed.match(/^[-*•]\s*(.+)$/);
    if (ordered) {
      flushParagraph();
      if (!list || list.type !== "ol") {
        flushList();
        list = { type: "ol", items: [], start: parseInt(ordered[1], 10) };
      }
      list.items.push(ordered[2]);
      return;
    }
    if (bullet) {
      flushParagraph();
      if (!list || list.type !== "ul") {
        flushList();
        list = { type: "ul", items: [] };
      }
      list.items.push(bullet[1]);
      return;
    }
    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();

  if (!nodes.length) {
    return <p>{renderInline(normalized)}</p>;
  }
  return nodes;
}

export default function AssistantChat() {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "assistant",
      content: "Hi! I’m your trading assistant. Ask me about your positions, risk, or a symbol.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const savedSignaturesRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    (async () => {
      try {
        const rawSig = localStorage.getItem(SAVED_SIG_KEY);
        if (rawSig) {
          const arr = JSON.parse(rawSig);
          if (Array.isArray(arr)) {
            savedSignaturesRef.current = new Set(
              arr.filter((sig: unknown): sig is string => typeof sig === "string")
            );
          }
        }
      } catch {}

      const applySavedSignatures = (items: Msg[]): Msg[] =>
        items.map(item => {
          if (item.role !== "assistant") return item;
          const sig = messageSignature(item);
          if (item.saved) {
            savedSignaturesRef.current.add(sig);
            return item;
          }
          if (savedSignaturesRef.current.has(sig)) {
            return { ...item, saved: true };
          }
          return item;
        });

      let loaded = false;
      try {
        const r = await api.assistantChatLog(200);
        const arr = (r as any)?.messages || [];
        if (Array.isArray(arr) && arr.length) {
          const msgs: Msg[] = arr.map((m: any) => ({
            role: m.role === "assistant" ? "assistant" : "user",
            content: String(m.content || ""),
            saved: !!m.saved,
            settingsApplied: !!m.settingsApplied,
          }));
          if (msgs.length) {
            setMessages(applySavedSignatures(msgs));
            loaded = true;
          }
        }
      } catch {}
      if (!loaded) {
        try {
          const raw = localStorage.getItem(STORAGE_KEY);
          if (raw) {
            const arr = JSON.parse(raw);
            if (Array.isArray(arr) && arr.length) {
              const msgs = applySavedSignatures(
                (arr as Msg[]).map(m => ({
                  ...m,
                  role: m.role === "assistant" ? "assistant" : "user",
                }))
              );
              setMessages(msgs);
              loaded = true;
            }
          }
        } catch {}
      }
      setHydrated(true);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const st = await GET<{ summary: string }>("/autopilot/style");
        if ((st as any)?.summary) {
          localStorage.setItem("assistant.style.prev", String((st as any).summary));
        }
      } catch {}
    })();
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, loading]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {}
    try {
      localStorage.setItem(
        SAVED_SIG_KEY,
        JSON.stringify(Array.from(savedSignaturesRef.current))
      );
    } catch {}
  }, [messages, hydrated]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    const next = [...messages, { role: "user", content: text } as Msg];
    setMessages(next);
    setInput("");
    setLoading(true);

    const markSaved = async (
      targetIndex: number,
      meta?: { saved?: boolean; styleSummary?: string | null }
    ) => {
      if (meta?.styleSummary !== undefined && meta.styleSummary !== null) {
        localStorage.setItem("assistant.style.prev", String(meta.styleSummary));
      }
      if (meta?.saved) {
        setMessages(m =>
          m.map((mm, i) => {
            if (i === targetIndex) {
              const next = { ...mm, saved: true };
              if (next.role === "assistant") {
                savedSignaturesRef.current.add(messageSignature(next));
              }
              return next;
            }
            return mm;
          })
        );
        return;
      }
      try {
        const st = await GET<{ summary: string }>("/autopilot/style");
        const summary = (st as any)?.summary || "";
        const prev = localStorage.getItem("assistant.style.prev") || "";
        if (summary) {
          localStorage.setItem("assistant.style.prev", String(summary));
        }
        if (summary && summary !== prev) {
          setMessages(m =>
            m.map((mm, i) => {
              if (i === targetIndex) {
                const next = { ...mm, saved: true };
                if (next.role === "assistant") {
                  savedSignaturesRef.current.add(messageSignature(next));
                }
                return next;
              }
              return mm;
            })
          );
        }
      } catch {}
    };

    try {
      const idx = next.length;
      let created = false;
      let savedMeta: { saved: boolean; styleSummary?: string } = { saved: false };
      const url = `${API_BASE}/assistant/chat_stream?q=${encodeURIComponent(text)}&include_context=1`;
      const es = new EventSource(url);
      es.onmessage = async ev => {
        if (!ev.data) return;
        if (ev.data === "__END__") {
          es.close();
          setLoading(false);
          const meta = savedMeta.saved
            ? { saved: true, styleSummary: savedMeta.styleSummary ?? null }
            : savedMeta.styleSummary !== undefined
            ? { styleSummary: savedMeta.styleSummary ?? null }
            : undefined;
          await markSaved(idx, meta);
          return;
        }
        if (ev.data.startsWith("__ACTIONS__|")) {
          try {
            const raw = ev.data.substring("__ACTIONS__|".length);
            const a = JSON.parse(raw);
            if (Array.isArray(a) && a.length) {
              setMessages(m => m.map((mm, i) => (i === idx ? { ...mm, settingsApplied: true } : mm)));
            }
          } catch {}
          return;
        }
        if (ev.data.startsWith("__MEM_SAVED__")) {
          let payload: any = null;
          if (ev.data.startsWith("__MEM_SAVED__|")) {
            const raw = ev.data.substring("__MEM_SAVED__|".length);
            try {
              payload = JSON.parse(raw);
            } catch {}
          }
          savedMeta.saved = true;
          if (payload && typeof payload.style_summary === "string") {
            savedMeta.styleSummary = payload.style_summary;
            localStorage.setItem("assistant.style.prev", String(payload.style_summary));
          }
          setMessages(m =>
            m.map((mm, i) => {
              if (i === idx) {
                const next = { ...mm, saved: true };
                if (next.role === "assistant") {
                  savedSignaturesRef.current.add(messageSignature(next));
                }
                return next;
              }
              return mm;
            })
          );
          try {
            window.dispatchEvent(
              new CustomEvent("assistant-memory-updated", { detail: payload || {} })
            );
          } catch {}
          return;
        }
        const chunk = ev.data || "";
        if (!created) {
          setMessages(m => {
            const head = m.slice(0, idx);
            const tail = m.slice(idx);
            return [...head, { role: "assistant", content: chunk } as Msg, ...tail];
          });
          created = true;
        } else {
          setMessages(m =>
            m.map((mm, i) => (i === idx ? { ...mm, content: (mm.content || "") + chunk } : mm))
          );
        }
      };
      es.onerror = async () => {
        es.close();
        let meta: { saved?: boolean; styleSummary?: string | null } | undefined;
        try {
          const r = await api.assistantChat(
            next.map(m => ({ role: m.role, content: m.content })),
            true
          );
          const reply = (r && (r as any).reply) || "(no reply)";
          setMessages(m => m.map((mm, i) => (i === idx ? { ...mm, content: String(reply) } : mm)));
          const actions = (r as any)?.actions || [];
          if (Array.isArray(actions) && actions.length) {
            setMessages(m => m.map((mm, i) => (i === idx ? { ...mm, settingsApplied: true } : mm)));
          }
          const memSaved = Boolean((r as any)?.mem_saved);
          const styleSummary = (r as any)?.style_summary ?? null;
          if (memSaved) {
            meta = { saved: true, styleSummary };
            if (styleSummary !== null) {
              localStorage.setItem("assistant.style.prev", String(styleSummary));
            }
            try {
              window.dispatchEvent(
                new CustomEvent("assistant-memory-updated", {
                  detail: { style_summary: styleSummary ?? undefined, memory: (r as any)?.memory },
                })
              );
            } catch {}
          } else if (styleSummary !== null) {
            meta = { styleSummary };
            localStorage.setItem("assistant.style.prev", String(styleSummary));
          }
        } catch (e: any) {
          setMessages(m =>
            m.map((mm, i) => (i === idx ? { ...mm, content: String(e?.message || e) } : mm))
          );
        } finally {
          setLoading(false);
          await markSaved(idx, meta);
        }
      };
    } catch {
      let meta: { saved?: boolean; styleSummary?: string | null } | undefined;
      try {
        const r = await api.assistantChat(
          next.map(m => ({ role: m.role, content: m.content })),
          true
        );
        const reply = (r && (r as any).reply) || "(no reply)";
        const actions = (r as any)?.actions || [];
        const applied = Array.isArray(actions) && actions.length > 0;
        setMessages([
          ...next,
          { role: "assistant", content: String(reply), ...(applied ? { settingsApplied: true } : {}) } as Msg,
        ]);
        const memSaved = Boolean((r as any)?.mem_saved);
        const styleSummary = (r as any)?.style_summary ?? null;
        if (memSaved) {
          meta = { saved: true, styleSummary };
          if (styleSummary !== null) {
            localStorage.setItem("assistant.style.prev", String(styleSummary));
          }
          try {
            window.dispatchEvent(
              new CustomEvent("assistant-memory-updated", {
                detail: { style_summary: styleSummary ?? undefined, memory: (r as any)?.memory },
              })
            );
          } catch {}
        } else if (styleSummary !== null) {
          meta = { styleSummary };
          localStorage.setItem("assistant.style.prev", String(styleSummary));
        }
        await markSaved(next.length, meta);
      } catch (e: any) {
        setMessages([...next, { role: "assistant", content: String(e?.message || e) }]);
      } finally {
        setLoading(false);
      }
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="chatbox">
      <div className="chat-list" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble-block">
              <div className="bubble">
                <div className="role">{m.role === "user" ? "You" : "Assistant"}</div>
                <div className="text">{renderRichMessage(m.content)}</div>
              </div>
              {m.role === "assistant" && (m.saved || m.settingsApplied) ? (
                <div className="label-row">
                  <svg
                    className="icon"
                    viewBox="0 0 16 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M2 8l3.5 3.5L14 3"
                      stroke="#a3e635"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span>{m.settingsApplied ? "Settings updated" : "Saved to memory"}</span>
                </div>
              ) : null}
            </div>
          </div>
        ))}
        {loading && <div className="typing">Assistant is typing…</div>}
      </div>
      <div className="chat-input">
        <textarea
          className="input"
          rows={3}
          placeholder="Ask about a symbol, risk, or decisions…"
          style={{ resize: "none" as any }}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
        />
        <button className="btn brand" onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
