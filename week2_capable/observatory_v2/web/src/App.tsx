import { Launcher } from "./Launcher";
import { LiveShell } from "./live/LiveShell";
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
  return <Launcher />;
}
