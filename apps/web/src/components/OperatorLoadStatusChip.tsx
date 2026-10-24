import { clsx } from "clsx";
import {
  deriveOperatorLoadStatus,
  type OperatorLoadStatusInput,
  operatorLoadStatusDisplayText,
} from "@/loads/operatorLoadStatus";

type Props = {
  load: OperatorLoadStatusInput;
  className?: string;
};

export default function OperatorLoadStatusChip({ load, className }: Props) {
  const result = deriveOperatorLoadStatus(load);
  const text = operatorLoadStatusDisplayText(result);
  const known = result.kind === "known";
  const color = (() => {
    if (!known) return "bg-gray-100 text-gray-600";
    switch (result.label) {
      case "Draft":
        return "bg-blue-100 text-blue-800";
      case "Unassigned":
        return "bg-amber-100 text-amber-900";
      case "Assigned":
        return "bg-sky-100 text-sky-900";
      case "In transit":
        return "bg-emerald-100 text-emerald-900";
      case "Delivered":
        return "bg-green-100 text-green-800";
      case "Cancelled":
        return "bg-gray-200 text-gray-700";
      default:
        return "bg-gray-100 text-gray-800";
    }
  })();

  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize",
        color,
        className,
      )}
    >
      {text}
    </span>
  );
}
