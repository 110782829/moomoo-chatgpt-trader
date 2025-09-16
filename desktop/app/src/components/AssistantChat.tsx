import { useEffect, useRef, useState } from "react";
import api, { API_BASE, GET } from "../api";

type Msg = { role: "user" | "assistant"; content: string; saved?: boolean };

const STORAGE_KEY = "assistant.chat.ui";

export default function AssistantChat() {
  const [messages, setMessages] = useState<Msg[]>([{
    role: "assistant",
    content: "Hi! I’m your trading assistant. Ask me about your positions, risk, or a symbol.",
  }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Load persisted chat on mount
  useEffect(() => {
    (async () => {
      try {
        // Prefer server log (shared with memory) so chat survives browser restarts
        const r = await api.assistantChatLog(200);
        const arr = (r as any)?.messages || [];
        if (Array.isArray(arr) && arr.length) {
          const msgs: Msg[] = arr.map((m: any) => ({ role: (m.role === 'assistant' ? 'assistant' : 'user'), content: String(m.content||''), saved: !!m.saved, ...(m.settingsApplied? {settingsApplied:true}: {}) } as any));
          if (msgs.length) { setMessages(msgs as Msg[]); return; }
        }
      } catch {}
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const arr = JSON.parse(raw);
          if (Array.isArray(arr) && arr.length) setMessages(arr as Msg[]);
        }
      } catch {}
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

  // Persist on change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {}
  }, [messages]);

  function escapeHtml(s: string){
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function formatMessage(s: string){
    let html = escapeHtml(String(s||''));
    // Convert newlines early so streamed lists render correctly
    html = html.replace(/\n/g, '<br/>');
    // Basic markdown: bold **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Numbered items and dash bullets on new lines
    html = html.replace(/(^|<br\/>)(\d+)\.\s*/g, '$1$2. ');
    html = html.replace(/(^|<br\/>)-\s*/g, '$1- ');
    // Break before dash following punctuation like ':' ';' or ')'
    html = html.replace(/([:\);])\s*-\s*/g, '$1<br/>- ');
    // Support bullets like •
    html = html.replace(/(^|<br\/>)[•]\s*/g, '$1- ');
    // Collapse excessive breaks
    html = html.replace(/(<br\/>){2,}/g, '<br/>' );
    return html;
  }

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    const next = [...messages, { role: "user", content: text } as Msg];
    setMessages(next);
    setInput("");
    setLoading(true);
    const markSaved = async (targetIndex: number) => {
      try {
        const st = await GET<{ summary: string }>("/autopilot/style");
        const summary = (st as any)?.summary || "";
        const prev = localStorage.getItem("assistant.style.prev") || "";
        if (summary) {
          localStorage.setItem("assistant.style.prev", String(summary));
        }
        if (summary && summary !== prev) {
          setMessages(m => m.map((mm, i) => i===targetIndex? ({...mm, saved: true}) : mm));
        }
      } catch {}
    };

    // Try streaming via SSE first for livelier feel; fall back to 1-shot
    try {
      const idx = next.length; // slot for assistant bubble
      let created = false;
      const url = `${API_BASE}/assistant/chat_stream?q=${encodeURIComponent(text)}&include_context=1`;
      const es = new EventSource(url);
      es.onmessage = async (ev) => {
        if (!ev.data) return;
        if (ev.data === "__END__") {
          es.close();
          setLoading(false);
          await markSaved(idx);
          return;
        }
        if (ev.data.startsWith("__ACTIONS__|")) {
          try {
            const raw = ev.data.substring("__ACTIONS__|".length);
            const a = JSON.parse(raw);
            if (Array.isArray(a) && a.length) {
              setMessages(m => m.map((mm, i) => i===idx? ({...mm, settingsApplied: true}) : mm));
            }
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
          setMessages(m => m.map((mm, i) => i===idx? ({...mm, content: (mm.content||"") + chunk}) : mm));
        }
      };
      es.onerror = async () => {
        es.close();
        try {
          const r = await api.assistantChat(next.map(m => ({ role: m.role, content: m.content })), true);
          const reply = (r && (r as any).reply) || "(no reply)";
          setMessages(m => m.map((mm, i) => i===idx? ({...mm, content: String(reply)}) : mm));
          const actions = (r as any)?.actions || [];
          if (Array.isArray(actions) && actions.length) {
            setMessages(m => m.map((mm, i) => i===idx? ({...mm, settingsApplied: true}) : mm));
          }
        } catch (e: any) {
          setMessages(m => m.map((mm, i) => i===idx? ({...mm, content: String(e?.message || e)}) : mm));
        } finally {
          setLoading(false);
          await markSaved(idx);
        }
      };
    } catch {
      try {
        const r = await api.assistantChat(next.map(m => ({ role: m.role, content: m.content })), true);
        const reply = (r && (r as any).reply) || "(no reply)";
        const actions = (r as any)?.actions || [];
        const applied = Array.isArray(actions) && actions.length > 0;
        setMessages([...next, { role: "assistant", content: String(reply), ...(applied ? { settingsApplied: true } : {}) } as any]);
        await markSaved(next.length);
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
                <div className="text" dangerouslySetInnerHTML={{__html: formatMessage(m.content)}} />
              </div>
              {m.role === 'assistant' && (m.saved || (m as any).settingsApplied) ? (
                <div className="label-row">
                  <svg className="icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M2 8l3.5 3.5L14 3" stroke="#a3e635" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  <span>{(m as any).settingsApplied ? 'Settings updated' : 'Saved to bot memory'}</span>
                </div>
              ) : null}
            </div>
          </div>
        ))}
        {loading && <div className="typing">Assistant is typing…</div>}
      </div>
      <div className="chat-input">
        <textarea className="input" rows={3} placeholder="Ask about a symbol, risk, or decisions…" style={{ resize:'none' as any }}
          value={input} onChange={e=>setInput(e.target.value)} onKeyDown={onKey} />
        <button className="btn brand" onClick={send} disabled={loading || !input.trim()}>Send</button>
      </div>
    </div>
  );
}
