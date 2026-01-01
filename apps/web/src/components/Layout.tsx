import { ReactNode } from "react";
import SidebarNav from "./SidebarNav";

type Props = {
  children: ReactNode;
};

export default function Layout({ children }: Props) {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <div className="flex">
        <SidebarNav />
        <main className="flex-1 p-6 space-y-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
