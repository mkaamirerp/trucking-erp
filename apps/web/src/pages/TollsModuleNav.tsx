import { Link } from "react-router-dom";
import { OPS } from "../routes";

export default function TollsModuleNav({ active }: { active: "csv" | "pdf" | "manual" }) {
  const linkClass = (key: "csv" | "pdf" | "manual") =>
    key === active
      ? "text-sm font-semibold text-[var(--trk-text)] underline underline-offset-4"
      : "text-sm text-[var(--trk-accent)] underline-offset-2 hover:underline";
  return (
    <nav className="flex flex-wrap gap-4 text-sm">
      <Link to={OPS.TOLLS} className={linkClass("csv")}>
        CSV File Imports
      </Link>
      <Link to={OPS.TOLLS_PDF_REVIEWS} className={linkClass("pdf")}>
        PDF Reviews
      </Link>
      <Link to={OPS.TOLLS_MANUAL_ENTRY} className={linkClass("manual")}>
        Manual Entry
      </Link>
    </nav>
  );
}
