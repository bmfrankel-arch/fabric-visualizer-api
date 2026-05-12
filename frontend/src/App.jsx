import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import VisualizePage from "./pages/VisualizePage";
import FabricsPage from "./pages/FabricsPage";
import FurniturePage from "./pages/FurniturePage";
import { BRAND } from "./api";

function App() {
  const isBrandMode = Boolean(BRAND.key);
  const rootStyle = BRAND.accent ? { "--brand-accent": BRAND.accent } : undefined;

  return (
    <BrowserRouter>
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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
