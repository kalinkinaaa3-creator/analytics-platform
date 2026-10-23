import { useEffect, useRef, useState } from "react";
import { Confirmation } from "./primitives";

export function useConfirm() {
  const [message, setMessage] = useState("");
  const pending = useRef(null);
  useEffect(() => () => { pending.current?.(false); pending.current = null; }, []);
  function confirm(text) {
    if (pending.current) return Promise.resolve(false);
    return new Promise(resolve => { pending.current = resolve; setMessage(text); });
  }
  function answer(value) {
    pending.current?.(value); pending.current = null; setMessage("");
  }
  return [confirm, <Confirmation key="confirmation" message={message} onAnswer={answer} />];
}
