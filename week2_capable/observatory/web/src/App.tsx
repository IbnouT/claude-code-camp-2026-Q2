import { Launcher } from "./Launcher";
import { LiveShell } from "./live/LiveShell";
import { SessionRoute } from "./sessions/SessionRoute";
import { ExperimentRoute } from "./experiments/ExperimentRoute";
import { KnowledgeRoute } from "./knowledge/KnowledgeRoute";
import { liveIdentity } from "./routes";
import { useTheme } from "./theme";

export function App() {
  const [theme, setTheme] = useTheme();

  if (window.location.pathname === "/live") {
    return (
      <LiveShell
        identity={liveIdentity(window.location)}
        theme={theme}
        onThemeChange={setTheme}
      />
    );
  }
  if (window.location.pathname === "/sessions") {
    return (
      <SessionRoute
        theme={theme}
        onThemeChange={setTheme}
      />
    );
  }
  if (window.location.pathname === "/knowledge") {
    return (
      <KnowledgeRoute
        theme={theme}
        onThemeChange={setTheme}
      />
    );
  }
  if (window.location.pathname === "/experiments") {
    return (
      <ExperimentRoute
        theme={theme}
        onThemeChange={setTheme}
      />
    );
  }
  return <Launcher theme={theme} onThemeChange={setTheme} />;
}
