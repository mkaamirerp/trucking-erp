import { useParams } from "react-router-dom";

type Props = {
  title: string;
  description?: string;
};

export default function AdminPlaceholderPage({ title, description }: Props) {
  const { "*": subpath } = useParams();
  const displayTitle = subpath ? `${title} (${subpath})` : title;

  return (
    <div className="space-y-6">
      <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[var(--trk-text)]">
        {displayTitle}
      </h1>
      <p className="text-[var(--trk-text-muted)]">
        {description || "This page is a placeholder. Configuration options will be added here."}
      </p>
      <div className="rounded-xl border border-dashed border-[var(--trk-border-strong)] bg-[var(--trk-bg)]/50 p-12 text-center text-[var(--trk-text-muted)]">
        Coming soon
      </div>
    </div>
  );
}
