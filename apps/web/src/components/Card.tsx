import { ReactNode } from "react";
import { clsx } from "clsx";

type Props = {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function Card({ title, actions, children, className }: Props) {
  return (
    <div className={clsx("bg-white border border-gray-200 rounded-lg shadow-sm", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          {title && <h2 className="text-sm font-semibold text-gray-900">{title}</h2>}
          {actions && <div className="flex items-center space-x-2">{actions}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
