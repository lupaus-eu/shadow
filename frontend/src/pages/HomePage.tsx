import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createOrganisation,
  fetchOrganisations
} from "../api/organisations";
import type { OrganisationDto } from "../api/organisations";

function sortOrganisations(items: OrganisationDto[]): OrganisationDto[] {
  return [...items].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
  );
}

export default function HomePage() {
  const navigate = useNavigate();

  const [organisations, setOrganisations] = useState<OrganisationDto[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [createError, setCreateError] = useState("");

  const selectedOrganisation = useMemo(
    () => organisations.find((item) => item.id === selectedOrgId) ?? null,
    [organisations, selectedOrgId]
  );

  useEffect(() => {
    const ac = new AbortController();
    let ignore = false;

    async function loadOrganisations() {
      try {
        setLoading(true);
        setLoadError("");
        const items = sortOrganisations(await fetchOrganisations(ac.signal));

        if (ignore) return;
        setOrganisations(items);
        setSelectedOrgId((current) => current || items[0]?.id || "");
      } catch (error) {
        const err = error as { name?: string; message?: string };
        if (ignore || err.name === "AbortError") return;
        setLoadError(error instanceof Error ? error.message : "Unknown error");
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadOrganisations();

    return () => {
      ignore = true;
      ac.abort();
    };
  }, []);

  function openSelectedOrganisation() {
    if (!selectedOrgId) return;

    navigate(`/schatten/${selectedOrgId}/org-states`, {
      state: { organisationName: selectedOrganisation?.name ?? "" }
    });
  }

  async function onCreateOrganisation() {
    const name = newOrgName.trim();
    if (!name) {
      setCreateError("Organisation name is required.");
      return;
    }

    try {
      setCreating(true);
      setCreateError("");
      const created = await createOrganisation({ name });

      setOrganisations((current) =>
        sortOrganisations([
          ...current.filter((item) => item.id !== created.id),
          created
        ])
      );
      setSelectedOrgId(created.id);
      setNewOrgName("");
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="center-page">
      <section className="home-panel" aria-labelledby="home-title">
        <p className="eyebrow">Schatten</p>
        <h1 id="home-title" className="display-title">
          Select organisation
        </h1>
        <p className="muted">
          Choose an organisation to open the workspace, or create a new one.
        </p>

        <div className="form-row">
          <label className="form-label" htmlFor="organisation-select">
            Organisation
          </label>
          <select
            id="organisation-select"
            className="select"
            value={selectedOrgId}
            onChange={(event) => setSelectedOrgId(event.target.value)}
            disabled={loading || organisations.length === 0}
          >
            {organisations.length === 0 ? (
              <option value="">
                {loading ? "Loading..." : "No organisations available"}
              </option>
            ) : (
              organisations.map((organisation) => (
                <option key={organisation.id} value={organisation.id}>
                  {organisation.name}
                </option>
              ))
            )}
          </select>
          <button
            className="btn btn--primary"
            type="button"
            onClick={openSelectedOrganisation}
            disabled={loading || !selectedOrgId}
          >
            Open organisation
          </button>
        </div>

        <hr className="divider" />

        <div className="form-row">
          <label className="form-label" htmlFor="new-organisation-name">
            Create new organisation
          </label>
          <input
            id="new-organisation-name"
            className="input"
            value={newOrgName}
            onChange={(event) => setNewOrgName(event.target.value)}
            placeholder="Organisation name"
            disabled={creating}
          />
          <button
            className="btn btn--secondary"
            type="button"
            onClick={() => void onCreateOrganisation()}
            disabled={creating || !newOrgName.trim()}
          >
            {creating ? "Creating..." : "Create organisation"}
          </button>
        </div>

        {loadError ? (
          <div className="alert alert--danger" role="alert">
            <p className="alert__title">API error</p>
            <p className="alert__text">{loadError}</p>
          </div>
        ) : null}

        {createError ? (
          <div className="alert alert--danger" role="alert">
            <p className="alert__title">Create error</p>
            <p className="alert__text">{createError}</p>
          </div>
        ) : null}
      </section>
    </main>
  );
}
