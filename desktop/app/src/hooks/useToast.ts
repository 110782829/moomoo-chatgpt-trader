import { useRef, useState } from "react";

/** Simple toast state */
export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  function show(message: string, timeout = 2800) {
    setMsg(message);
    window.clearTimeout(timer.current!);
    timer.current = window.setTimeout(() => setMsg(null), timeout);
  }
  return { msg, show };
}
