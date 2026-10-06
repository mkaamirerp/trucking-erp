import { Link } from "react-router-dom";
import { OPS } from "../routes";

export default function TollsModuleNav({ active }: { active: "upload" | "manual" }) {
  const linkClass = (key: "upload" | "manual") =>
    key === active
      ? "text-sm font-semibold text-[var(--trk-text)] underline underline-offset-4"
      : "text-sm text-[var(--trk-accent)] underline-offset-2 hover:underline";
  return (
    <nav className="flex flex-wrap gap-4 text-sm">
      <Link to={OPS.TOLLS} className={linkClass("upload")}>
        Upload
      </Link>
      <Link to={OPS.TOLLS_MANUAL_ENTRY} className={linkClass("manual")}>
        Manual Entry
      </Link>
    </nav>
  );
}
