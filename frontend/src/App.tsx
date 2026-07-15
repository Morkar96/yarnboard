import { Navigate, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import ProtectedRoute from "./components/ProtectedRoute";
import CommunityPage from "./pages/CommunityPage";
import LoginPage from "./pages/LoginPage";
import MySavedPage from "./pages/MySavedPage";
import MyUploadsPage from "./pages/MyUploadsPage";
import PatternDetailPage from "./pages/PatternDetailPage";
import RegisterPage from "./pages/RegisterPage";
import ReviewPatternPage from "./pages/ReviewPatternPage";
import SubmitPatternPage from "./pages/SubmitPatternPage";

export default function App() {
  return (
    <>
      <NavBar />
      <main className="app-content">
        <Routes>
          <Route path="/" element={<Navigate to="/community" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/community" element={<CommunityPage />} />
          <Route path="/pattern/:id" element={<PatternDetailPage />} />
          <Route
            path="/submit"
            element={
              <ProtectedRoute>
                <SubmitPatternPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/submit/review"
            element={
              <ProtectedRoute>
                <ReviewPatternPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/mine"
            element={
              <ProtectedRoute>
                <MyUploadsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/saved"
            element={
              <ProtectedRoute>
                <MySavedPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </>
  );
}
