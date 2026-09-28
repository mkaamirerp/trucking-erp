import { Navigate } from "react-router-dom";
import { OPS } from "../routes";

/** Internal route — Fuel home is the only operator entry for completed activity. */
export default function FuelBvdHistoryPage() {
  return <Navigate to={OPS.FUEL} replace />;
}
