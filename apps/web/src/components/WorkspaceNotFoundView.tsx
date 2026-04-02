/**
 * Shown when the user is on a tenant subdomain (e.g. demo.truckerp.me) but that workspace does not exist.
 */
export function WorkspaceNotFoundView({ slug }: { slug: string }) {
  return (
    <div className="trk-auth">
      <div className="trk-auth-wrap">
        <div className="trk-brand">
          <div className="trk-badge">🚚</div>
          <div>
            <h1>Trucking ERP</h1>
            <p>Secure fleet operations platform</p>
          </div>
        </div>
        <div className="trk-card">
          <h2>Workspace not found</h2>
          <p className="trk-foot">
            There is no workspace for <span className="font-semibold">{slug}</span>. The link may be wrong or the workspace was removed.
          </p>
          <div className="mt-6 space-y-3">
            <a href="https://truckerp.me" className="trk-primary block w-full text-center py-2">
              Go to main site
            </a>
            <a href="https://truckerp.me/signup" className="block w-full text-center py-2 text-sm text-slate-400 hover:text-slate-300">
              Create a new workspace
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
