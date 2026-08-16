import { Container } from "react-bootstrap";
import { Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import ProtectedRoute from "./components/ProtectedRoute";
import UpdateBanner from "./components/UpdateBanner";
import CommunityPage from "./pages/CommunityPage";
import EditPatternPage from "./pages/EditPatternPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import MySavedPage from "./pages/MySavedPage";
import MyUploadsPage from "./pages/MyUploadsPage";
import PatternDetailPage from "./pages/PatternDetailPage";
import RegisterPage from "./pages/RegisterPage";
import ReviewPatternPage from "./pages/ReviewPatternPage";
import StitchFiddlePage from "./pages/StitchFiddlePage";
import SubmitPatternPage from "./pages/SubmitPatternPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";

export default function App() {
  return (
    <>
      <NavBar />
      <UpdateBanner />
      <Container as="main" className="py-4">
        <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <HomePage />
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route
            path="/community"
            element={
              <ProtectedRoute>
                <CommunityPage />
              </ProtectedRoute>
            }
          />
          <Route path="/pattern/:id" element={<PatternDetailPage />} />
          <Route
            path="/pattern/:id/edit"
            element={
              <ProtectedRoute>
                <EditPatternPage />
              </ProtectedRoute>
            }
          />
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
          <Route
            path="/stitch-fiddle"
            element={
              <ProtectedRoute>
                <StitchFiddlePage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </Container>
    </>
  );
}
