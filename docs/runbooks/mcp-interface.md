# The MCP interface for agents

Agents the people of an Organization choose (for example Claude with a custom connector) read and
change Yearclocks through `/api/mcp` (ADR-0037, ADR-0038). Authentik signs the person in through its
own provider, `Yearclock MCP`. The interface is off until you turn it on.

## Turn it on

1. **Settings** in `.env.production` (`.env` locally; keys in `.env.production.example`):
   - `MCP_OIDC_CLIENT_ID`: the client id of the MCP provider; it is the token audience.
   - `MCP_OIDC_CLIENT_SECRET`: a long random secret. It is shared by every Organization and shown
     to Owners and Admins on the "Connect an agent" page. Never commit it.
   - `MCP_OIDC_ISSUER`: the provider's issuer, `https://<identity host>/application/o/yearclock-mcp/`
     (the slug is the application slug in the blueprint).
   - `MCP_ENABLED=true`.
2. Copy the host's files first (`rsync` in `first-deployment.md` section 7); the blueprint and the Caddy route live there, not in the images. Then apply the blueprint so Authentik creates the provider: `make deploy` (production) or `make up`
   (local); `make authentik-apply` forces it. `authentik-config-init` applies
   `authentik/blueprints/yearclock-mcp-application.yaml` when the file or these values changed.
3. Check:
   - `https://<site>/.well-known/oauth-protected-resource/api/mcp` returns JSON (not an HTML page) that names the MCP
     issuer, and `https://<identity host>/application/o/yearclock-mcp/.well-known/openid-configuration`
     returns `200`. Without a token, `POST /api/mcp` returns `401`.
   - Connect a real client (MCP Inspector, or Claude's custom connector with the client id and
     secret), sign in, and list the Organizations.

The backend reaches Authentik over the Compose network (`OIDC_INTERNAL_BASE_URL`) to fetch the
signing keys, as it does for the web login.

## Add another MCP client

The blueprint lists strict redirect URLs (Claude's `claude.ai` and `claude.com` callbacks). Add
the client's redirect URL there and apply the blueprint. Check the client's own documentation for the
exact callback; never use a wildcard for a remote client.

## Change the secret

Change `MCP_OIDC_CLIENT_SECRET`, run `make deploy` (the blueprint updates the provider), and give the
new value to the people who connected agents; their connectors stop signing in until they update it.
Tokens already issued stay valid until they expire.

## Stop it

- One Organization: its Owners or Admins turn the switch off on the "Connect an agent" page, or you
  **Block** it in the Platform area (Organizations); the Organization cannot lift a block.
- Everyone: `MCP_ENABLED=false` and redeploy; `/api/mcp` is then not served.
- One person: remove the membership, or disable the user in Authentik (a token already issued works
  until it expires).

## When something fails

| Symptom | Likely cause |
| --- | --- |
| `401` for every request | The token's audience is not `MCP_OIDC_CLIENT_ID`, its issuer is not `MCP_OIDC_ISSUER`, or the backend cannot fetch the keys (check `OIDC_INTERNAL_BASE_URL` and that Authentik trusts the forwarded scheme, `AUTHENTIK_TRUSTED_PROXY_CIDRS`). |
| "This sign-in has no Yearclock account" | The person has not signed in to the Yearclock web application yet, or the account is a Platform account. |
| "MCP access ... is turned off" or "blocked by the operator" | The Organization switch or the operator block. |
| The metadata address returns the web application's HTML page, and signing in lands in Yearclock instead of returning to the agent | The running Caddy still has an old Caddyfile (a file mount keeps the old inode after a deploy). Run `make reload-edge`; the first time after upgrading, recreate Caddy once: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate caddy`. Without the metadata, the agent cannot find the Authentik provider and falls back to the site's own sign-in. |
| Metadata is `404` from the public address | Caddy does not forward `/.well-known/oauth-protected-resource*`, or `MCP_ENABLED` is not true. |

## Developing and testing

`mcp` 2.3.0 needs `starlette>=0.48` on Python 3.14, which conflicts with the pinned FastAPI 0.115.6
(`starlette<0.42`). On Python 3.12, the version the backend image uses, the pins resolve together.
Run the backend tests on Python 3.12 (for example a venv made with `python3.12 -m venv`, then
`pip install -r backend/requirements-dev.txt`); a 3.14 virtual environment cannot import `mcp` next to this FastAPI.

## Tools for models

Agents that work with a model use these tools (every one takes `organization_id`; ADR-0046). They call the same functions as the web application, so roles, the read-only state, `expected_version`, limits and audit apply, and every call appears in the call log. A refusal comes back as a readable tool error that carries the reason (for example `chain_broken` with the event, element and cause, or `parent_moved_on` with the suggestion).

| Tool | Arguments | What it does |
| --- | --- | --- |
| `list_models` | | The models, with `base_line_id` |
| `get_model` | `model_id`, `line_id?` | The lines, the metamodel and the nodes and connections of one line (the Base line by default) after its last event; `latest_event` is the event `create_node` writes into |
| `list_lines` | `model_id` | The Base line first, then the Scenarios, each with its parent and branch event |
| `list_events` | `model_id`, `line_id` | The line's own events in order: date, title, note, planned, change counts, branching Scenarios |
| `get_state` | `model_id`, `line_id`, `event_id?` or `as_of?` (YYYY-MM-DD) | The graph after an event or on a date (the present state when neither is given), with what the event added, updated and removed |
| `create_scenario` | `model_id`, `name`, `branch_event_id`, `description?` | A Scenario from the state after any event; copies that line's metrics |
| `add_event` | `model_id`, `line_id`, `occurred_on`, `title`, `note?`, `changes?` | A dated event with ordered changes (`add_node`, `remove_node`, `update_node`, `add_connection`, `remove_connection`, `reroute_connection`, `change_connection_type`); Base line: Owner or Admin |
| `update_event` | `model_id`, `event_id`, `expected_version`, `occurred_on?`, `title?`, `note?`, `changes?` | Changes the fields given; `changes` replaces the list; an empty `note` clears it |
| `delete_event` | `model_id`, `event_id`, `expected_version` | Deletes an event (destructive); refused when another line branches from it or the chain would break |
| `adopt_scenario` | `model_id`, `line_id`, `expected_version?` | Appends the Scenario's events to its parent (destructive: the Scenario is deleted unless it has child Scenarios); Owner or Admin for the Base line |
| `create_node`, `create_connection` | `model_id`, `event_id`, ... | Canvas edits as changes inside an event |
| `create_model`, `create_metric`, `set_metric_values`, `run_simulation`, `generate_analysis`, `set_analysis_summary`, `add_proposal`, `list_metrics`, `get_metric_series`, `list_simulations`, `get_simulation`, `get_analysis` | as before; the metric and simulation tools take `line_id` | |

The version tools (`create_version`, `merge_version`, `get_version_changes`) no longer exist; a connector that remembered them must refresh its tool list.
