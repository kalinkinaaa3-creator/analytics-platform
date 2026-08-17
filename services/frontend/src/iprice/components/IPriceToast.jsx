import { useEffect } from "react";


export function IPriceToast({
  message,
  type = "success",
  onClose,
}) {
  useEffect(() => {
    if (!message) {
      return undefined;
    }

    const timerId = window.setTimeout(
      onClose,
      10000,
    );

    return () => {
      window.clearTimeout(timerId);
    };
  }, [message, type, onClose]);

  if (!message) {
    return null;
  }

  return (
    <div
      className={[
        "iprice-toast",
        `iprice-toast--${type}`,
      ].join(" ")}
      role="status"
    >
      <span>{message}</span>

      <button
        type="button"
        aria-label="Закрыть уведомление"
        onClick={onClose}
      >
        ×
      </button>
    </div>
  );
}
