import { NavLink, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Ask Onboarding</span>
        <nav>
          <NavLink to="/" end>
            Chat
          </NavLink>
          <NavLink to="/documents">Documents</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="*" element={<p className="notice">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
