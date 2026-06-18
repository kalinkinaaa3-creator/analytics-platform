export function AccessDeniedPage() {
  return (
    <div
      style={{
        fontFamily: "Helvetica, sans-serif",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        height: "80vh",
        background: "#f8d7da",
        color: "#721c24",
      }}
    >
      <div
        style={{
          background: "#f5c6cb",
          padding: "20px",
          borderRadius: "5px",
        }}
      >
        <h2>Доступ запрещён</h2>
        <p>У вас нет прав на этот раздел.</p>
      </div>
    </div>
  );
}