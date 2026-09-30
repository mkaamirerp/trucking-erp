import { ReactNode } from "react";
import TopNav from "./TopNav";

type Props = {
  children: ReactNode;
};

export default function Layout({ children }: Props) {
  return (
    <div className="trk-app-shell">
      <TopNav />
      {/* min-h-0 + min-w-0: children can scroll (including wide tables) without clipping */}
      <main className="trk-app-main">{children}</main>
    </div>
  );
}
