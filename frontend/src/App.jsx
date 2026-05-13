import { useEffect } from "react";
import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom";
import VisualizePage from "./pages/VisualizePage";
import FabricsPage from "./pages/FabricsPage";
import FurniturePage from "./pages/FurniturePage";
import AdminUsagePage from "./pages/AdminUsagePage";
import { BRAND } from "./api";
import { track } from "./analytics";

function PageViewTracker() {
  const location = useLocation();
  useEffect(() => {
    track("page_view", { brand: BRAND.key || null, path: location.pathname });
  }, [location.pathname]);
  return null;
}

function App() {
  const isBrandMode = Boolean(BRAND.key);
  const rootStyle = BRAND.accent ? { "--brand-accent": BRAND.accent } : undefined;

  return (
    <BrowserRouter>
      <PageViewTracker />
      <div className="app" style={rootStyle}>
        <nav className="sidebar">
          <div className="sidebar-logo">
            {BRAND.logoUrl && (
              <img src={BRAND.logoUrl} alt={BRAND.name} className="sidebar-brand-logo" />
            )}
            {isBrandMode ? `${BRAND.name} × Dorell Fabrics` : "Fabric Visualizer"}
          </div>
          <ul className="sidebar-nav">
            <li>
              <NavLink to="/" end>Visualize</NavLink>
            </li>
            {!isBrandMode && (
              <>
                <li><NavLink to="/fabrics">Dorell Fabrics</NavLink></li>
                <li><NavLink to="/furniture">Furniture</NavLink></li>
              </>
            )}
          </ul>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<VisualizePage />} />
            {!isBrandMode && <Route path="/fabrics" element={<FabricsPage />} />}
            {!isBrandMode && <Route path="/furniture" element={<FurniturePage />} />}
            {!isBrandMode && <Route path="/admin/usage" element={<AdminUsagePage />} />}
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
