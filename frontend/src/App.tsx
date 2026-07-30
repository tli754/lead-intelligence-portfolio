import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { ImportPage } from "./pages/ImportPage";
import { JobsPage } from "./pages/JobsPage";

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/companies" replace />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        <Route path="/jobs" element={<JobsPage />} />
      </Route>
    </Routes>
  );
}

export default App;
