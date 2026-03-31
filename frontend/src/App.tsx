import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import "./App.css";
import type { User } from "./types/index";
import { Layout } from "./components/Layout";
import LoginPage from "./pages/Login";
import RegisterPage from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import ToolsPage from "./pages/Tools";
import ChatPage from "./pages/Chat";
import AdminPage from "./pages/Admin";
import ProfilePage from "./pages/Profile";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAgentThinking, setIsAgentThinking] = useState(false);

  useEffect(() => {
    async function fetchMe() {
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        const data = await res.json();
        if (res.ok && data.user) {
          setUser(data.user);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchMe();
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-slate-500">
        加载中...
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage setUser={setUser} />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="*"
          element={
            <Layout user={user} setUser={setUser} isAgentThinking={isAgentThinking}>
              {user ? (
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/tools" element={<ToolsPage user={user} />} />
                  <Route path="/agent" element={<ChatPage user={user} setIsAgentThinking={setIsAgentThinking} />} />
                  <Route path="/admin" element={<AdminPage user={user} />} />
                  <Route path="/profile" element={<ProfilePage user={user} setUser={setUser} />} />
                  <Route path="*" element={<Navigate to="/" />} />
                </Routes>
              ) : (
                <Navigate to="/login" />
              )}
            </Layout>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
