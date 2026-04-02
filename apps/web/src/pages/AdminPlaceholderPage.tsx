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
      <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#e8edf5]">
        {displayTitle}
      </h1>
      <p className="text-[#94a3b8]">
        {description || "This page is a placeholder. Configuration options will be added here."}
      </p>
      <div className="rounded-xl border border-dashed border-[#334155] bg-[#0a0e14]/50 p-12 text-center text-[#64748b]">
        Coming soon
      </div>
    </div>
  );
}
