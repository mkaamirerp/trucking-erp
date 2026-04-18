import { ReactNode } from "react";
import TopNav from "./TopNav";

type Props = {
  children: ReactNode;
};

export default function Layout({ children }: Props) {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--trk-bg)] text-[var(--trk-text)]">
      <TopNav />
      {/* flex-1 + min-h-0: children (e.g. Dispatch) can own internal scroll without main height collapse */}
      <main className="flex min-h-0 flex-1 flex-col space-y-6 overflow-auto bg-transparent p-6 [scrollbar-gutter:stable]">
        {children}
      </main>
    </div>
  );
}
