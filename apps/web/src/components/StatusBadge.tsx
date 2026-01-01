import { clsx } from "clsx";

type Props = {
  status: string;
};

export default function StatusBadge({ status }: Props) {
  const normalized = status?.toUpperCase?.() ?? "";
  const color = (() => {
    if (["FINALIZED", "CLOSED", "PAID"].includes(normalized)) return "bg-green-100 text-green-800";
    if (["DRAFT", "GENERATED", "OPEN", "UNPAID"].includes(normalized)) return "bg-blue-100 text-blue-800";
    if (["VOIDED"].includes(normalized)) return "bg-gray-200 text-gray-700";
    if (["PARTIAL"].includes(normalized)) return "bg-yellow-100 text-yellow-800";
    return "bg-gray-100 text-gray-800";
  })();
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", color)}>
      {status}
    </span>
  );
}
