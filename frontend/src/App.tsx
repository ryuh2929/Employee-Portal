import { useEffect, useState } from "react";

type ApiStatus = "loading" | "connected" | "unavailable";

function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("loading");

  useEffect(() => {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

    fetch(`${apiBaseUrl}/health`)
      .then((response) => {
        if (!response.ok) throw new Error("API health check failed");
        setApiStatus("connected");
      })
      .catch(() => setApiStatus("unavailable"));
  }, []);

  return (
    <main>
      <section className="status-card">
        <p className="eyebrow">Employee Portal</p>
        <h1>프로젝트 기반 구성이 준비되었습니다.</h1>
        <p>로그인과 직원 관리 기능은 다음 단계부터 추가합니다.</p>
        <p role="status" className={`api-status api-status--${apiStatus}`}>
          Backend: {apiStatus}
        </p>
      </section>
    </main>
  );
}

export default App;

