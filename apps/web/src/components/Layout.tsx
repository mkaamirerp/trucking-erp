import { ReactNode } from "react";
import SidebarNav from "./SidebarNav";

type Props = {
  children: ReactNode;
};

export default function Layout({ children }: Props) {
  return (
    <div className="min-h-screen bg-[#080a0f] text-[#e8edf5]">
      <div className="flex">
        <SidebarNav />
        <main className="flex-1 overflow-auto bg-transparent p-6 space-y-6">{children}</main>
      </div>
    </div>
  );
}
