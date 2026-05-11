// Centralized Chart.js registration so any chart component shares the same setup.
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  LineController,
  BarController,
  Tooltip,
  Legend,
  Title,
} from "chart.js";

let registered = false;

export function ensureRegistered() {
  if (registered) return;
  ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    LineController,
    BarController,
    Tooltip,
    Legend,
    Title,
  );
  registered = true;
}
