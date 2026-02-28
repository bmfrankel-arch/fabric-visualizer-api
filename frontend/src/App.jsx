import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import VisualizePage from "./pages/VisualizePage";
import FabricsPage from "./pages/FabricsPage";
import FurniturePage from "./pages/FurniturePage";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="sidebar-logo">Fabric Visualizer</div>
          <ul className="sidebar-nav">
            <li>
              <NavLink to="/" end>
                Visualize
              </NavLink>
            </li>
            <li>
              <NavLink to="/fabrics">Dorell Fabrics</NavLink>
            </li>
            <li>
              <NavLink to="/furniture">Furniture</NavLink>
            </li>
          </ul>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<VisualizePage />} />
            <Route path="/fabrics" element={<FabricsPage />} />
            <Route path="/furniture" element={<FurniturePage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
