import { Link } from "react-router-dom";
import { PLATFORM } from "../routes";
import PlatformUnlockLoginForm from "../components/PlatformUnlockLoginForm";

export default function PlatformUnlockLoginPage() {
  return (
    <div className="max-w-xl space-y-4">
      <div>
        <Link to={PLATFORM.HOME} className="text-sm text-slate-400 hover:text-slate-200">
          ← Platform home
        </Link>
        <h1 className="text-xl font-semibold text-white tracking-tight mt-2">Testing: unlock login</h1>
      </div>
      <PlatformUnlockLoginForm />
    </div>
  );
}
