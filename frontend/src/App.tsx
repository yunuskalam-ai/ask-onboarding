import { Route, Routes } from "react-router-dom";
import { RequireRole } from "./auth";
import AppHeader from "./components/AppHeader";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import HomePage from "./pages/HomePage";
import OverviewPage from "./pages/OverviewPage";
import PeoplePage from "./pages/PeoplePage";
import ProjectDocsPage from "./pages/ProjectDocsPage";
import SignInPage from "./pages/SignInPage";
import TicketsPage from "./pages/TicketsPage";

export default function App() {
  return (
    <div className="app">
      <AppHeader />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/sign-in" element={<SignInPage />} />
          <Route path="/chat" element={<RequireRole><ChatPage /></RequireRole>} />
          <Route path="/documents" element={<RequireRole><DocumentsPage /></RequireRole>} />
          <Route path="/tickets" element={<RequireRole><TicketsPage /></RequireRole>} />
          <Route path="/overview" element={<RequireRole roles={["admin"]}><OverviewPage /></RequireRole>} />
          <Route path="/project-docs/:slug?" element={<RequireRole roles={["admin"]}><ProjectDocsPage /></RequireRole>} />
          <Route path="/people" element={<RequireRole roles={["admin"]}><PeoplePage /></RequireRole>} />
          <Route path="*" element={<p className="page notice">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
